"""Тесты системных эндпоинтов ClicKit Cloud: `/healthz`, `/version`, `/metrics`.

FastAPI не входит в desktop-зависимости (`requirements.txt`), поэтому в
Windows-матрице CI без `requirements-service.txt` модуль пропускается.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from core.ir.nodes import SCENARIO_VERSION
from service.app.config import ServiceConfigError, Settings

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from service.app.main import create_app  # noqa: E402
from service.app.version import SERVICE_NAME, SERVICE_VERSION  # noqa: E402

#: Валидный ключ записи для тестов (≥ 16 символов).
API_KEY = "test-key-0123456789"
#: Коммит «сборки» в тестах.
GIT_SHA = "abc1234"


@pytest.fixture()
def client() -> Iterator[TestClient]:
    """Клиент приложения с явными настройками и запущенным lifespan."""
    app = create_app(Settings(api_key=API_KEY, git_sha=GIT_SHA))
    with TestClient(app) as test_client:
        yield test_client


def test_healthz_returns_ok(client: TestClient) -> None:
    """Liveness отвечает 200 и не требует БД."""
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": SERVICE_NAME,
        "version": SERVICE_VERSION,
    }


def test_version_reports_build_information(client: TestClient) -> None:
    """Версия отдаёт данные сборки и версию формата IR из core."""
    response = client.get("/version")

    assert response.status_code == 200
    assert response.json() == {
        "service": SERVICE_NAME,
        "version": SERVICE_VERSION,
        "git_sha": GIT_SHA,
        "built_at": "",
        "ir_format_version": SCENARIO_VERSION,
    }


def test_metrics_returns_prometheus_text(client: TestClient) -> None:
    """Заготовка метрик — текст Prometheus с меткой сборки."""
    response = client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "version=0.0.4" in response.headers["content-type"]
    assert (
        f'clikit_build_info{{version="{SERVICE_VERSION}",git_sha="{GIT_SHA}"}} 1'
    ) in response.text


def test_openapi_contains_system_endpoints(client: TestClient) -> None:
    """OpenAPI доступен и содержит системные эндпоинты контракта."""
    response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert {"/healthz", "/version", "/metrics"} <= set(paths)


def test_startup_without_api_key_fails() -> None:
    """Без ключа записи приложение не поднимается (fail-closed)."""
    app = create_app(Settings())

    with pytest.raises(ServiceConfigError), TestClient(app):
        pass
