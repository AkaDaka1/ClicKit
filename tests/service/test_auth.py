"""Тесты авторизации ClicKit Cloud по API-ключу (`docs/api.md` §2).

Проверяется контракт: публичное чтение, 401 без/с неверным ключом, 403 при
недостаточной роли, разделение write/admin-ключей и отсутствие секрета в
ответах и журнале. Формат ошибок и `X-Request-ID` — в `test_request_id.py`.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("sqlalchemy")

from fastapi.testclient import TestClient  # noqa: E402

from service.app.config import Settings  # noqa: E402
from service.app.db import Database  # noqa: E402
from service.app.main import create_app  # noqa: E402
from tests.service.conftest import API_KEY, publish_body  # noqa: E402

#: Административный ключ для тестов (≥ 16 символов).
ADMIN_KEY = "admin-key-0123456789"
#: Заведомо неверный ключ.
WRONG_KEY = "wrong-key-0123456789"


@contextmanager
def make_client(database: Database, **overrides: object) -> Iterator[TestClient]:
    """Клиент приложения с явными настройками (без заголовка по умолчанию).

    Args:
        database: Изолированная БД теста.
        **overrides: Переопределения `Settings` (например, `admin_api_key`).

    Yields:
        `TestClient` с ключами из настроек, но без автоматического заголовка.
    """
    settings = Settings(api_key=API_KEY, db_url=database.url, **overrides)  # type: ignore[arg-type]
    app = create_app(settings, database=database)
    with TestClient(app) as test_client:
        yield test_client


def test_read_endpoints_are_public(database: Database) -> None:
    """`GET /v1/scenarios` не требует ключа (`docs/api.md` §2)."""
    with make_client(database) as client:
        response = client.get("/v1/scenarios")

    assert response.status_code == 200
    assert response.json()["total"] == 0


def test_publish_without_key_is_401(database: Database) -> None:
    """Публикация без `X-API-Key` — 401 problem+json."""
    with make_client(database) as client:
        response = client.post("/v1/scenarios", json=publish_body())

    assert response.status_code == 401
    body = response.json()
    assert body["type"] == "urn:clikit:error:unauthorized"
    assert body["status"] == 401
    assert response.headers["content-type"].startswith("application/problem+json")


def test_publish_with_wrong_key_is_401(database: Database) -> None:
    """Неверный `X-API-Key` — 401, а не 403: роль не определена."""
    with make_client(database) as client:
        response = client.post(
            "/v1/scenarios",
            json=publish_body(),
            headers={"X-API-Key": WRONG_KEY},
        )

    assert response.status_code == 401
    assert response.json()["type"] == "urn:clikit:error:unauthorized"


def test_publish_with_write_key_is_201(client: TestClient) -> None:
    """Ключ записи публикует сценарий (общий fixture добавляет заголовок)."""
    response = client.post("/v1/scenarios", json=publish_body())

    assert response.status_code == 201


def test_admin_key_cannot_publish(database: Database) -> None:
    """Роли разделены: admin-ключ не даёт права на публикацию — 403."""
    with make_client(database, admin_api_key=ADMIN_KEY) as client:
        response = client.post(
            "/v1/scenarios",
            json=publish_body(),
            headers={"X-API-Key": ADMIN_KEY},
        )

    assert response.status_code == 403
    assert response.json()["type"] == "urn:clikit:error:forbidden"


def test_delete_without_key_is_401(database: Database) -> None:
    """Удаление без ключа — 401 (`docs/api.md` §5.8)."""
    with make_client(database) as client:
        created = client.post(
            "/v1/scenarios",
            json=publish_body(),
            headers={"X-API-Key": API_KEY},
        ).json()
        response = client.delete(f"/v1/scenarios/{created['id']}")

    assert response.status_code == 401


def test_delete_with_write_key_when_admin_configured_is_403(
    database: Database,
) -> None:
    """При заданном admin-ключе write-ключ удалять не может — 403."""
    with make_client(database, admin_api_key=ADMIN_KEY) as client:
        created = client.post(
            "/v1/scenarios",
            json=publish_body(),
            headers={"X-API-Key": API_KEY},
        ).json()
        response = client.delete(
            f"/v1/scenarios/{created['id']}",
            headers={"X-API-Key": API_KEY},
        )

    assert response.status_code == 403
    assert response.json()["type"] == "urn:clikit:error:forbidden"


def test_delete_with_admin_key_is_204(database: Database) -> None:
    """Admin-ключ удаляет сценарий, созданный ключом записи."""
    with make_client(database, admin_api_key=ADMIN_KEY) as client:
        created = client.post(
            "/v1/scenarios",
            json=publish_body(),
            headers={"X-API-Key": API_KEY},
        ).json()
        response = client.delete(
            f"/v1/scenarios/{created['id']}",
            headers={"X-API-Key": ADMIN_KEY},
        )
        listing = client.get("/v1/scenarios")

    assert response.status_code == 204
    assert listing.json()["total"] == 0


def test_delete_with_write_key_when_admin_not_configured_is_204(
    client: TestClient,
) -> None:
    """Без admin-ключа удаление доступно обычному ключу записи."""
    created = client.post("/v1/scenarios", json=publish_body()).json()

    response = client.delete(f"/v1/scenarios/{created['id']}")

    assert response.status_code == 204


def test_key_is_not_echoed_in_error(database: Database) -> None:
    """Секрет не попадает в тело ошибки (`docs/api.md` §2)."""
    secret = "very-secret-key-0123456789"
    with make_client(database) as client:
        response = client.post(
            "/v1/scenarios",
            json=publish_body(),
            headers={"X-API-Key": secret},
        )

    assert response.status_code == 401
    assert secret not in response.text


def test_key_is_not_logged(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    """Ключ не пишется в журнал; строка запроса коррелируется `request_id`."""
    secret = "very-secret-key-0123456789"
    incoming = "log-check-request-id-0123456789ab"

    with caplog.at_level(logging.INFO):
        client.post(
            "/v1/scenarios",
            json=publish_body(),
            headers={"X-API-Key": secret, "X-Request-ID": incoming},
        )

    assert secret not in caplog.text
    assert incoming in caplog.text
    assert "POST /v1/scenarios" in caplog.text


def test_openapi_declares_api_key_security(client: TestClient) -> None:
    """OpenAPI показывает схему `ApiKey` и требование к публикации."""
    document = client.get("/openapi.json").json()

    schemes = document["components"]["securitySchemes"]
    assert schemes["ApiKey"]["type"] == "apiKey"
    assert schemes["ApiKey"]["in"] == "header"
    assert schemes["ApiKey"]["name"] == "X-API-Key"
    assert document["paths"]["/v1/scenarios"]["post"]["security"] == [{"ApiKey": []}]
