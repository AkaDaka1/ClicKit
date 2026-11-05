"""Статические проверки локального compose ClicKit Cloud (M7 T4.1).

Реальный чекпоинт задачи — `docker compose -f docker-compose.cloud.yml up -d`,
проверка `/healthz` и сохранности данных после `down`/`up`. Эти тесты страхуют
от регрессий в конфигурации compose: потеря миграций, тома или ожидания БД
обнаруживается только при ручном запуске, а секрет, попавший в YAML, — уже
утечка.
"""

from __future__ import annotations

import re
from pathlib import Path

#: Корень репозитория: файл лежит в tests/service/.
REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE = REPO_ROOT / "docker-compose.cloud.yml"
ENV_EXAMPLE = REPO_ROOT / ".env.example"

#: Обязательные переменные окружения compose-файла.
REQUIRED_ENV_VARS = ("CLICKIT_API_KEY", "POSTGRES_PASSWORD")


def _compose_text() -> str:
    """Прочитать compose-файл как текст."""
    return COMPOSE.read_text(encoding="utf-8")


def _service_block(name: str) -> str:
    """Вырезать блок сервиса `name` из compose-файла.

    Args:
        name: Имя сервиса (`db`, `migrate`, `api`).

    Returns:
        Текст блока сервиса без строки-заголовка.
    """
    text = _compose_text()
    match = re.search(
        rf"^  {name}:\n(.*?)(?=^  [a-z][a-z0-9-]*:|\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    assert match is not None, f"в compose нет сервиса {name}"
    return match.group(1)


def test_compose_runs_api_with_postgres_16() -> None:
    """Compose описывает API, БД и одноразовые миграции на PostgreSQL 16."""
    text = _compose_text()

    assert "name: clikit-cloud" in text
    assert "image: postgres:16" in _service_block("db")
    assert "docker/Dockerfile.service" in text
    assert "service_completed_successfully" in text


def test_migrations_run_before_api() -> None:
    """Схема применяется Alembic-миграциями до старта API (ADR №52)."""
    migrate = _service_block("migrate")

    assert "alembic" in migrate
    assert "upgrade" in migrate and "head" in migrate
    # CMD образа (аргументы uvicorn) должен быть очищен при замене ENTRYPOINT.
    assert re.search(r"^\s+command: \[\]$", migrate, re.MULTILINE)


def test_api_waits_for_healthy_db_and_migrations() -> None:
    """API не стартует, пока БД не готова и миграции не завершились."""
    api = _service_block("api")

    assert "condition: service_healthy" in api
    assert "condition: service_completed_successfully" in api
    assert "pg_isready" in _service_block("db")


def test_database_uses_named_volume() -> None:
    """Данные PostgreSQL лежат в именованном томе и переживают перезапуск."""
    text = _compose_text()

    assert "pgdata:/var/lib/postgresql/data" in text
    assert re.search(r"^volumes:\n  pgdata:\s*$", text, re.MULTILINE)


def test_compose_requires_secrets_from_environment() -> None:
    """Секретов в compose нет: значения приходят только из env/.env."""
    text = _compose_text()

    for name in REQUIRED_ENV_VARS:
        assert f"${{{name}:?" in text, f"{name} должен быть обязательным"
    # Каждое значение секрета — подстановка `${...}`, а не литерал.
    for name in (*REQUIRED_ENV_VARS, "CLICKIT_ADMIN_API_KEY"):
        values = re.findall(rf"^\s+{name}:\s*(.+)$", text, re.MULTILINE)
        assert values, f"нет значения {name}"
        assert all(value.strip().startswith("${") for value in values), values


def test_api_port_is_configurable() -> None:
    """Порт API на хосте настраивается, внутри контейнера — 8000."""
    api = _service_block("api")

    assert '"${CLICKIT_API_PORT:-8000}:8000"' in api


def test_env_example_documents_required_variables() -> None:
    """`.env.example` перечисляет обязательные переменные без реальных секретов."""
    text = ENV_EXAMPLE.read_text(encoding="utf-8")

    for name in REQUIRED_ENV_VARS:
        assert re.search(rf"^{name}=", text, re.MULTILINE), f"нет {name}"
    assert "CLICKIT_ADMIN_API_KEY=" in text
    assert "CLICKIT_API_PORT=" in text
