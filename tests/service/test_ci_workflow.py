"""Статические проверки job `service-tests` в CI (M7 T5.1).

Реальный чекпоинт задачи — зелёный job в GitHub Actions на PR. Эти тесты
страхуют от регрессий в конфигурации: забытый сервис PostgreSQL, отключённое
покрытие или запуск не тех тестов обнаруживаются только при следующем прогоне
CI, а не при локальной правке.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

#: Корень репозитория: файл лежит в tests/service/.
REPO_ROOT = Path(__file__).resolve().parents[2]
CI = REPO_ROOT / ".github" / "workflows" / "ci.yml"
PYPROJECT = REPO_ROOT / "pyproject.toml"

#: Минимальное покрытие сервиса из плана M7 (T5.1).
MIN_COVERAGE = 80


def _ci_text() -> str:
    """Прочитать workflow CI как текст."""
    return CI.read_text(encoding="utf-8")


def _job_block(name: str) -> str:
    """Вырезать блок job `name` из `ci.yml`.

    Args:
        name: Идентификатор job (`lint`, `tests`, `service-tests`, …).

    Returns:
        Текст блока job без строки-заголовка.
    """
    text = _ci_text()
    match = re.search(
        rf"^  {re.escape(name)}:\n(.*?)(?=^  [a-z][a-z0-9-]*:|\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    assert match is not None, f"в ci.yml нет job {name}"
    return match.group(1)


def test_service_tests_job_exists_on_linux() -> None:
    """Отдельный job сервиса идёт на Linux и не смешивается с Windows-матрицей."""
    block = _job_block("service-tests")

    assert "runs-on: ubuntu-latest" in block
    # Windows-тесты desktop не ставят FastAPI/PostgreSQL — job должен быть свой.
    assert "python -m pytest tests/service" in block


def test_service_tests_job_uses_real_postgres_16() -> None:
    """Тесты сервиса проверяют схему на настоящем PostgreSQL 16."""
    block = _job_block("service-tests")

    assert "image: postgres:16" in block
    assert "pg_isready" in block
    assert "CLICKIT_TEST_DB_URL:" in block
    # Подключение к сервису контейнера должно идти через localhost раннера.
    assert "localhost:5432" in block


def test_service_tests_job_installs_service_requirements() -> None:
    """Job ставит только зависимости сервиса, а не требования GUI."""
    block = _job_block("service-tests")

    assert "python -m pip install -r requirements-service-test.txt" in block
    assert re.search(r"-r requirements\.txt\b", block) is None


def test_service_tests_job_enforces_coverage_and_reports() -> None:
    """Покрытие включено, а JUnit/coverage-отчёты сохраняются артефактом."""
    block = _job_block("service-tests")

    assert "--cov" in block
    assert "coverage.xml" in block
    assert "service-junit.xml" in block
    assert "if: always()" in block


def test_coverage_config_matches_plan() -> None:
    """Порог покрытия и источник отчёта зафиксированы в `pyproject.toml`."""
    with PYPROJECT.open("rb") as stream:
        config = tomllib.load(stream)

    run = config["tool"]["coverage"]["run"]
    report = config["tool"]["coverage"]["report"]

    assert run["source"] == ["service"]
    assert run["branch"] is True
    assert report["fail_under"] >= MIN_COVERAGE
