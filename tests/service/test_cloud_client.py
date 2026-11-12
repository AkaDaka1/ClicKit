"""Тесты клиента ClicKit Cloud (`cloud/client.py`, M7 T4.2).

Сеть подменяется `httpx.MockTransport`: проверяются коды ответов, разбор
problem+json в иерархию `CloudError`, паузы между попытками и то, что 4xx
не ретраятся (`docs/api.md` §10).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from cloud import client as cloud_client
from cloud.client import (
    CloudAuthError,
    CloudClient,
    CloudConflictError,
    CloudError,
    CloudNotFoundError,
    CloudServerError,
    CloudTooLargeError,
    CloudValidationError,
)

#: Пример IR, совпадающий с `tests/service/conftest.SAMPLE_SCENARIO`.
SAMPLE_IR: dict[str, Any] = {
    "version": 1,
    "name": "demo",
    "nodes": [{"type": "click", "x": 100, "y": 200}],
}

#: Метаданные сценария в формате ответа `POST /v1/scenarios`.
CREATED: dict[str, Any] = {
    "id": "11111111-1111-4111-8111-111111111111",
    "name": "demo",
    "description": "",
    "sha256": "a" * 64,
    "created_at": "2026-11-02T10:00:00Z",
    "updated_at": "2026-11-02T10:00:00Z",
    "url": "/v1/scenarios/11111111-1111-4111-8111-111111111111",
}


def make_client(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    api_key: str | None = "test-key-0123456789",
    attempts: int = 3,
    sleep: list[float] | None = None,
    jitter: float = 0.0,
) -> CloudClient:
    """Собрать клиент с mock-transport и «записанными» паузами.

    Args:
        handler: Обработчик `httpx.MockTransport`.
        api_key: Ключ записи или `None`.
        attempts: Число попыток.
        sleep: Список, куда пишутся паузы вместо реальных `time.sleep`.
        jitter: Доля разброса паузы (0 — детерминированные паузы).

    Returns:
        Готовый клиент (закрывается тестом).
    """
    client = CloudClient(
        "http://cloud.test",
        api_key=api_key,
        attempts=attempts,
        jitter=jitter,
        transport=httpx.MockTransport(handler),
    )
    if sleep is not None:
        client._sleep = sleep.append  # type: ignore[method-assign]
    return client


def json_response(status: int, payload: Any) -> httpx.Response:
    """Ответ с JSON-телом."""
    return httpx.Response(status, json=payload, headers={"X-Request-ID": "rid-1"})


def problem(
    status: int,
    *,
    detail: str = "ошибка",
    type_urn: str = "urn:clikit:error:bad-request",
    issues: list[dict[str, str]] | None = None,
) -> httpx.Response:
    """Ответ problem+json (`docs/api.md` §4)."""
    body: dict[str, Any] = {
        "type": type_urn,
        "title": "Ошибка",
        "status": status,
        "detail": detail,
        "instance": "/v1/scenarios",
        "request_id": "rid-1",
    }
    if issues is not None:
        body["errors"] = issues
    return httpx.Response(
        status,
        content=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/problem+json",
            "X-Request-ID": "rid-1",
        },
    )


def test_publish_returns_metadata_and_sends_key() -> None:
    """Публикация отправляет ключ, тело по контракту и читает `url`."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return json_response(201, CREATED)

    with make_client(handler) as client:
        published = client.publish(
            SAMPLE_IR,
            name="demo",
            description="из теста",
            idempotency_key="key-0001",
        )

    assert published.id == CREATED["id"]
    assert published.url == "/v1/scenarios/" + CREATED["id"]
    request = seen[0]
    assert request.method == "POST"
    assert request.url.path == "/v1/scenarios"
    assert request.headers["X-API-Key"] == "test-key-0123456789"
    assert request.headers["Idempotency-Key"] == "key-0001"
    body = json.loads(request.content)
    assert body == {
        "scenario": SAMPLE_IR,
        "name": "demo",
        "description": "из теста",
    }


def test_publish_requires_key_before_network() -> None:
    """Без ключа публикация падает до запроса (401)."""

    def handler(_request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("запрос не должен уходить без ключа")

    with make_client(handler, api_key=None) as client:
        with pytest.raises(CloudAuthError) as excinfo:
            client.publish(SAMPLE_IR)
    assert excinfo.value.status == 401


def test_download_returns_document_and_quotes_id() -> None:
    """Скачивание отдаёт документ и экранирует id в пути."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return json_response(200, SAMPLE_IR)

    with make_client(handler) as client:
        document = client.download("../../etc/passwd")

    assert document == SAMPLE_IR
    assert seen[0].url.raw_path == b"/v1/scenarios/..%2F..%2Fetc%2Fpasswd"


def test_list_builds_page() -> None:
    """Список превращается в `ScenarioPage` с метаданными."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["limit"] == "5"
        assert request.url.params["offset"] == "10"
        return json_response(
            200,
            {"items": [CREATED], "total": 42, "limit": 5, "offset": 10},
        )

    with make_client(handler) as client:
        page = client.list(limit=5, offset=10)

    assert page.total == 42
    assert page.limit == 5
    assert page.offset == 10
    assert [item.id for item in page.items] == [CREATED["id"]]


def test_delete_accepts_204() -> None:
    """Удаление возвращает `None` на 204."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(204)

    with make_client(handler) as client:
        assert client.delete(CREATED["id"]) is None
    assert seen[0].method == "DELETE"


def test_report_crash_returns_receipt() -> None:
    """Crash-отчёт уходит без необходимости ключа и возвращает квитанцию."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return json_response(
            202,
            {
                "id": "22222222-2222-4222-8222-222222222222",
                "received_at": "2026-11-02T10:00:00Z",
            },
        )

    with make_client(handler, api_key=None) as client:
        receipt = client.report_crash(
            app_version="1.0.0",
            os="Windows 11",
            error_hash="b" * 64,
            traceback="Traceback ...",
        )

    assert receipt.id == "22222222-2222-4222-8222-222222222222"
    assert "X-API-Key" not in seen[0].headers
    body = json.loads(seen[0].content)
    assert body["traceback"] == "Traceback ..."


@pytest.mark.parametrize(
    ("response", "exception"),
    [
        (problem(401, type_urn="urn:clikit:error:unauthorized"), CloudAuthError),
        (problem(403, type_urn="urn:clikit:error:forbidden"), CloudAuthError),
        (problem(404, type_urn="urn:clikit:error:not-found"), CloudNotFoundError),
        (problem(409, type_urn="urn:clikit:error:conflict"), CloudConflictError),
        (
            problem(413, type_urn="urn:clikit:error:payload-too-large"),
            CloudTooLargeError,
        ),
        (problem(422, type_urn="urn:clikit:error:validation"), CloudValidationError),
        (problem(400), CloudError),
    ],
)
def test_4xx_maps_to_hierarchy_without_retry(
    response: httpx.Response,
    exception: type[CloudError],
) -> None:
    """Каждый 4xx даёт своё исключение и не повторяется."""
    calls: list[int] = []
    sleeps: list[float] = []

    def handler(_request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return response

    with make_client(handler, sleep=sleeps) as client:
        with pytest.raises(exception) as excinfo:
            client.download(CREATED["id"])

    assert len(calls) == 1
    assert sleeps == []
    assert excinfo.value.status == response.status_code
    assert excinfo.value.request_id == "rid-1"
    assert excinfo.value.type_urn == response.json()["type"]


def test_validation_error_carries_issues() -> None:
    """422 передаёт пути ошибок из problem+json в `issues`."""
    issues = [{"path": "nodes[0].x", "message": "нет обязательного поля 'x'"}]

    def handler(_request: httpx.Request) -> httpx.Response:
        return problem(422, issues=issues)

    with make_client(handler) as client:
        with pytest.raises(CloudValidationError) as excinfo:
            client.download(CREATED["id"])

    assert excinfo.value.issues == issues
    assert "request_id=rid-1" in str(excinfo.value)


def test_5xx_is_retried_with_backoff_then_fails() -> None:
    """Три 5xx подряд — три запроса, паузы 0.5 и 1 с, затем `CloudServerError`."""
    calls: list[int] = []
    sleeps: list[float] = []

    def handler(_request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return problem(503, detail="БД недоступна")

    with make_client(handler, sleep=sleeps) as client:
        with pytest.raises(CloudServerError) as excinfo:
            client.list()

    assert len(calls) == 3
    assert sleeps == [0.5, 1.0]
    assert "3 попыток" in str(excinfo.value)
    assert excinfo.value.status == 503
    assert excinfo.value.request_id == "rid-1"


def test_5xx_then_success_returns_payload() -> None:
    """После 500 повтор возвращает успешный ответ."""
    calls: list[int] = []

    def handler(_request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) == 1:
            return problem(500)
        return json_response(200, SAMPLE_IR)

    with make_client(handler) as client:
        assert client.download(CREATED["id"]) == SAMPLE_IR
    assert len(calls) == 2


def test_timeout_is_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    """Таймаут считается повторяемой ошибкой; вторая попытка успешна."""
    calls: list[int] = []
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) == 1:
            raise httpx.ReadTimeout("timeout", request=request)
        return json_response(200, SAMPLE_IR)

    with make_client(handler, sleep=sleeps) as client:
        assert client.download(CREATED["id"]) == SAMPLE_IR

    assert len(calls) == 2
    assert sleeps == [0.5]


def test_network_error_exhausts_attempts() -> None:
    """Сетевая ошибка на всех попытках превращается в `CloudServerError`."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with make_client(handler, attempts=2) as client:
        with pytest.raises(CloudServerError) as excinfo:
            client.list()

    assert "2 попыток" in str(excinfo.value)


def test_jitter_keeps_pause_within_bounds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """С jitter пауза остаётся в пределах ±25 % базовой."""
    monkeypatch.setattr(cloud_client.random, "uniform", lambda a, b: b)
    client = CloudClient("http://cloud.test", jitter=0.25)
    try:
        assert client._pause(0) == pytest.approx(0.625)
        assert client._pause(1) == pytest.approx(1.25)
    finally:
        client.close()


def test_invalid_json_on_success_is_server_error() -> None:
    """Невалидный JSON успешного ответа — `CloudServerError`, а не ValueError."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json")

    with make_client(handler) as client:
        with pytest.raises(CloudServerError):
            client.download(CREATED["id"])


@pytest.mark.parametrize(
    "kwargs",
    [
        {"base_url": "cloud.test"},
        {"base_url": "http://cloud.test", "attempts": 0},
        {"base_url": "http://cloud.test", "attempts": 11},
        {"base_url": "http://cloud.test", "timeout": 0},
        {"base_url": "http://cloud.test", "jitter": 1.5},
    ],
)
def test_invalid_constructor_arguments(kwargs: dict[str, Any]) -> None:
    """Неверные параметры конструктора дают `ValueError`."""
    with pytest.raises(ValueError):
        CloudClient(**kwargs)
