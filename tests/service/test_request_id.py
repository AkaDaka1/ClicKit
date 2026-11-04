"""Тесты корреляции запросов ClicKit Cloud (`docs/api.md` §3, §4).

Проверяется: `X-Request-ID` есть на успешных и ошибочных ответах, валидный
входящий идентификатор пробрасывается, невалидный заменяется UUID4,
`.request_id` в problem+json совпадает с заголовком, а необработанные ошибки
и ошибки валидации FastAPI не выпадают из единого формата.
"""

from __future__ import annotations

import logging

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("sqlalchemy")

from fastapi.testclient import TestClient  # noqa: E402

from service.app.config import Settings  # noqa: E402
from service.app.db import Database  # noqa: E402
from service.app.main import create_app  # noqa: E402
from service.app.request_id import is_valid_request_id  # noqa: E402
from tests.service.conftest import API_KEY, publish_body  # noqa: E402

#: Валидный входящий идентификатор (32–64 символа `[A-Za-z0-9._-]`).
VALID_ID = "client-request-id-0123456789abcdef"
#: Заведомо невалидные значения: короткое, длинное, с пробелом.
INVALID_IDS = [
    "short",
    "x" * 65,
    "has space in the middle and is long enough",
]


def test_success_response_has_generated_request_id(client: TestClient) -> None:
    """Успешный ответ тоже содержит `X-Request-ID` (контракт §3)."""
    response = client.get("/healthz")

    header = response.headers.get("X-Request-ID")
    assert response.status_code == 200
    assert header is not None
    assert is_valid_request_id(header)


def test_valid_incoming_id_is_echoed(client: TestClient) -> None:
    """Валидный клиентский идентификатор пробрасывается без изменений."""
    response = client.get("/healthz", headers={"X-Request-ID": VALID_ID})

    assert response.headers["X-Request-ID"] == VALID_ID


@pytest.mark.parametrize("value", INVALID_IDS)
def test_invalid_incoming_id_is_replaced(client: TestClient, value: str) -> None:
    """Невалидный идентификатор не попадает в ответ — генерируется UUID4."""
    response = client.get("/healthz", headers={"X-Request-ID": value})

    header = response.headers["X-Request-ID"]
    assert header != value
    assert is_valid_request_id(header)


def test_non_ascii_request_id_is_invalid() -> None:
    """Кириллица/пробелы не проходят алфавит `[A-Za-z0-9._-]` (§3)."""
    from service.app.request_id import sanitize_request_id

    assert not is_valid_request_id("и" * 40)
    replacement = sanitize_request_id("и" * 40)
    assert replacement != "и" * 40
    assert is_valid_request_id(replacement)


def test_problem_json_uses_same_request_id(client: TestClient) -> None:
    """`request_id` в problem+json совпадает с заголовком ответа (§4)."""
    response = client.get(
        "/v1/scenarios/00000000-0000-4000-8000-000000000000",
        headers={"X-Request-ID": VALID_ID},
    )

    assert response.status_code == 404
    assert response.headers["X-Request-ID"] == VALID_ID
    assert response.json()["request_id"] == VALID_ID


def test_unknown_route_is_problem_json(client: TestClient) -> None:
    """Неизвестный путь — 404 problem+json, а не JSON FastAPI по умолчанию."""
    response = client.get("/definitely-not-a-route")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["type"] == "urn:clikit:error:not-found"
    assert is_valid_request_id(response.headers["X-Request-ID"])


def test_method_not_allowed_is_problem_json(client: TestClient) -> None:
    """Неподдерживаемый метод — 405 problem+json с заголовком `Allow`."""
    response = client.delete("/healthz")

    assert response.status_code == 405
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["type"] == "urn:clikit:error:method-not-allowed"
    assert "allow" in response.headers


def test_query_validation_is_problem_json(client: TestClient) -> None:
    """Ошибка параметров FastAPI приходит путём контракта, а не `detail`."""
    response = client.get("/v1/scenarios?limit=0")

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["type"] == "urn:clikit:error:validation"
    assert body["errors"][0]["path"] == "limit"
    assert is_valid_request_id(body["request_id"])


def test_body_limit_echoes_request_id(client: TestClient) -> None:
    """413 от middleware до маршрутизации сохраняет корреляцию."""
    huge = b'{"name":"' + b"x" * (1_048_576 + 10) + b'"}'

    response = client.post(
        "/v1/scenarios",
        content=huge,
        headers={"Content-Type": "application/json", "X-Request-ID": VALID_ID},
    )

    assert response.status_code == 413
    assert response.headers["X-Request-ID"] == VALID_ID
    assert response.json()["request_id"] == VALID_ID


def test_unhandled_error_is_500_problem_json(
    database: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Неожиданное исключение — 500 problem+json без деталей и traceback."""
    from service.app.api.v1 import scenarios as scenarios_module

    def boom(self: object, **kwargs: object) -> tuple[list[object], int]:
        raise RuntimeError("внутренняя деталь, которую нельзя отдавать")

    monkeypatch.setattr(scenarios_module.SqlScenarioRepository, "list_page", boom)
    app = create_app(
        Settings(api_key=API_KEY, db_url=database.url),
        database=database,
    )

    with TestClient(app, raise_server_exceptions=False) as failing:
        response = failing.get("/v1/scenarios", headers={"X-Request-ID": VALID_ID})

    assert response.status_code == 500
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["type"] == "urn:clikit:error:internal"
    assert body["request_id"] == VALID_ID
    assert "внутренняя деталь" not in response.text


def test_request_log_contains_request_id(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    """Строка access-журнала содержит идентификатор запроса."""
    with caplog.at_level(logging.INFO):
        client.get("/healthz", headers={"X-Request-ID": VALID_ID})

    assert VALID_ID in caplog.text
    assert "GET /healthz" in caplog.text


def test_publish_success_keeps_request_id(client: TestClient) -> None:
    """Заголовок сохраняется на 201, а не только на ошибках."""
    response = client.post(
        "/v1/scenarios",
        json=publish_body(),
        headers={"X-Request-ID": VALID_ID},
    )

    assert response.status_code == 201
    assert response.headers["X-Request-ID"] == VALID_ID
