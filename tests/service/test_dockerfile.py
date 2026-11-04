"""Статические проверки production-образа сервиса (M7 T3.2).

Сборка и запуск контейнера проверяются отдельно (чекпоинт задачи: образ
собирается, healthy, процесс не от root). Эти тесты страхуют от регрессий
в Dockerfile: потеря non-root пользователя, HEALTHCHECK или multi-stage
легко остаются незамеченными до ручного запуска.
"""

from __future__ import annotations

import re
from pathlib import Path

#: Корень репозитория: файл лежит в tests/service/.
REPO_ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = REPO_ROOT / "docker" / "Dockerfile.service"


def _dockerfile_text() -> str:
    """Прочитать Dockerfile сервиса."""
    return DOCKERFILE.read_text(encoding="utf-8")


def _instructions() -> str:
    """Оставить только инструкции Dockerfile, без строк комментариев."""
    return "\n".join(
        line
        for line in _dockerfile_text().splitlines()
        if not line.lstrip().startswith("#")
    )


def test_service_image_is_multi_stage() -> None:
    """Зависимости ставятся в builder, runtime копирует только venv и код."""
    text = _instructions()

    assert re.search(r"^FROM \S+ AS builder$", text, re.MULTILINE)
    assert re.search(r"^FROM \S+ AS runtime$", text, re.MULTILINE)
    assert "COPY --from=builder /opt/venv /opt/venv" in text
    assert re.search(r"^COPY requirements-service\.txt", text, re.MULTILINE)


def test_service_image_runs_as_non_root() -> None:
    """Контейнер не работает от root: есть отдельный пользователь и USER."""
    text = _instructions()

    assert "useradd --uid 10001" in text
    assert re.search(r"^USER 10001:10001$", text, re.MULTILINE)


def test_service_image_has_liveness_healthcheck() -> None:
    """HEALTHCHECK проверяет liveness без зависимости от БД."""
    text = _instructions()

    assert re.search(r"^HEALTHCHECK .*--start-period=\d+s", text, re.MULTILINE)
    assert "service.app.healthcheck" in text
    # Readiness с БД не должна перезапускать контейнер при недоступном Postgres.
    assert "/readyz" not in text


def test_service_image_uses_exec_form_entrypoint() -> None:
    """Exec-форма нужна, чтобы SIGTERM получал uvicorn, а не shell."""
    text = _instructions()

    assert 'ENTRYPOINT ["python", "-m", "uvicorn", "service.app.main:app"]' in text
    assert 'CMD ["--host", "0.0.0.0", "--port", "8000"' in text


def test_service_image_excludes_test_dependencies() -> None:
    """Тестовые зависимости не попадают в production-образ."""
    text = _instructions()

    assert "requirements-service-test.txt" not in text
    assert "pytest" not in text
