"""Тесты readiness-проверки: 200 при живой БД, 503 при сбое, без деталей."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("sqlalchemy")

from fastapi.testclient import TestClient  # noqa: E402

from service.app.config import Settings  # noqa: E402
from service.app.main import create_app  # noqa: E402
from tests.service.fakes import FakeDatabase  # noqa: E402

#: Валидный ключ записи для тестов (≥ 16 символов).
API_KEY = "test-key-0123456789"
#: URL БД-заглушки: в тестах соединение не устанавливается (БД поддельная).
DB_URL = "postgresql+psycopg://clikit:clikit@localhost:5432/clikit"


def _make_client(database: FakeDatabase) -> TestClient:
    """Клиент с явными настройками и поддельной БД."""
    app = create_app(Settings(api_key=API_KEY, db_url=DB_URL), database=database)
    return TestClient(app)


def test_readyz_returns_ready_when_database_is_available() -> None:
    """Доступная БД — 200, контрактное тело (`docs/api.md` §5.2)."""
    database = FakeDatabase(ready=True)
    with _make_client(database) as client:
        response = client.get("/readyz")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "checks": {"database": "ok"},
    }
    assert database.checks == 1


def test_readyz_returns_503_when_database_is_unavailable() -> None:
    """Недоступная БД — 503 и `database: error`, процесс остаётся живым."""
    database = FakeDatabase(ready=False)
    with _make_client(database) as client:
        response = client.get("/readyz")
        health = client.get("/healthz")

    assert response.status_code == 503
    assert response.json() == {
        "status": "unavailable",
        "checks": {"database": "error"},
    }
    assert health.status_code == 200


def test_readyz_does_not_leak_database_details() -> None:
    """В ответе нет ни URL, ни текста ошибки — только статус."""
    database = FakeDatabase(ready=False)
    with _make_client(database) as client:
        body = client.get("/readyz").text

    assert DB_URL not in body
    assert "psycopg" not in body
    assert "password" not in body.lower()


def test_database_is_disposed_on_shutdown() -> None:
    """Остановка приложения закрывает соединения с БД."""
    database = FakeDatabase()
    with _make_client(database):
        assert database.disposed is False

    assert database.disposed is True


def test_openapi_contains_readyz() -> None:
    """`/readyz` описан в OpenAPI вместе с ответом 503."""
    with _make_client(FakeDatabase()) as client:
        paths = client.get("/openapi.json").json()["paths"]

    assert "/readyz" in paths
    assert "503" in paths["/readyz"]["get"]["responses"]
