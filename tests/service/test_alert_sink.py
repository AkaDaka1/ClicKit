"""Проверка AlertSink (M8 T2.1, scripts/alert_sink.py).

Приёмник — крошечный HTTP-сервер на стандартной библиотеке: приём вебхука
Alertmanager v4, история для `GET /alerts`, единый формат. Python-код
покрывается обычными тестами, а контракт интеграции и compose страхуют
статические проверки. Запуск:
  python -m pytest tests/service/test_alert_sink.py
"""

from __future__ import annotations

import json
import threading
from http.client import HTTPConnection
from types import TracebackType

from scripts.alert_sink import (
    MAX_BODY_BYTES,
    AlertHistory,
    format_alert,
    make_server,
    summarize_alert,
)

#: Образец алерта Alertmanager v4: как его присылает `alertmanager.yml`.
SAMPLE_ALERT = {
    "status": "firing",
    "labels": {
        "alertname": "High5xx",
        "severity": "critical",
        "route": "/v1/scenarios",
    },
    "annotations": {"summary": "5xx > 1% за 5 минут"},
}


class _SinkApp:
    """Приёмник, запущенный в фоновом потоке на свободном порту."""

    def __init__(self, history: AlertHistory | None = None) -> None:
        self.server = make_server("127.0.0.1", 0, history)
        self.host, self.port = self.server.server_address
        self._thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self) -> _SinkApp:
        self._thread.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.server.shutdown()
        self.server.server_close()
        self._thread.join(timeout=5)


def _request(
    sink: _SinkApp, method: str, path: str, body: bytes | None = None
) -> tuple[int, dict]:
    """Выполнить запрос к приёмнику и вернуть статус и JSON-ответ."""
    conn = HTTPConnection(sink.host, sink.port, timeout=5)
    headers = {"Content-Type": "application/json"} if body is not None else {}
    conn.request(method, path, body=body, headers=headers)
    response = conn.getresponse()
    payload = json.loads(response.read().decode("utf-8"))
    conn.close()
    return response.status, payload


def _post_webhook(sink: _SinkApp, payload: object) -> tuple[int, dict]:
    """Отправить JSON на `/webhook`."""
    return _request(sink, "POST", "/webhook", json.dumps(payload).encode("utf-8"))


def test_webhook_records_alert_and_returns_count() -> None:
    """Вебхук записывает алерт и возвращает число принятых записей."""
    with _SinkApp() as sink:
        status, body = _post_webhook(sink, {"alerts": [SAMPLE_ALERT]})
        assert status == 200
        assert body == {"received": 1}

        status, alerts = _request(sink, "GET", "/alerts")
        assert status == 200
        assert len(alerts["alerts"]) == 1
        recorded = alerts["alerts"][0]
        assert recorded["status"] == "firing"
        assert recorded["alertname"] == "High5xx"
        assert recorded["severity"] == "critical"
        assert recorded["summary"] == "5xx > 1% за 5 минут"
        assert recorded["received_at"]


def test_webhook_requires_alerts_list() -> None:
    """Без поля `alerts` — 422 (формат Alertmanager v4)."""
    with _SinkApp() as sink:
        status, body = _post_webhook(sink, {"foo": 1})
        assert status == 422
        assert "alerts" in body["error"]


def test_invalid_json_returns_400() -> None:
    """Не-JSON тело — 400, сервер продолжает работать."""
    with _SinkApp() as sink:
        status, body = _request(sink, "POST", "/webhook", b"{not json")
        assert status == 400
        assert "JSON" in body["error"]
        assert _request(sink, "GET", "/healthz")[0] == 200


def test_healthz_ok_and_unknown_path_404() -> None:
    """`/healthz` — 200; незнакомый путь — 404."""
    with _SinkApp() as sink:
        status, body = _request(sink, "GET", "/healthz")
        assert status == 200
        assert body == {"status": "ok"}
        assert _request(sink, "GET", "/nope")[0] == 404
        assert _request(sink, "POST", "/nope")[0] == 404


def test_only_low_risk_fields_are_stored() -> None:
    """Лишние поля алерта не копируются в историю (принцип «не логировать всё»)."""
    with _SinkApp() as sink:
        alert = {
            **SAMPLE_ALERT,
            "labels": {**SAMPLE_ALERT["labels"], "secret": "must-not-be-kept"},
            "annotations": {**SAMPLE_ALERT["annotations"], "password": "x"},
        }
        assert _post_webhook(sink, {"alerts": [alert]})[0] == 200
        recorded = _request(sink, "GET", "/alerts")[1]["alerts"][0]
        assert "secret" not in json.dumps(recorded)
        assert "password" not in json.dumps(recorded)


def test_history_is_limited_and_ordered() -> None:
    """`AlertHistory` хранит последние N записей в порядке поступления."""
    history = AlertHistory(limit=2)
    history.add({"n": 1})
    history.add({"n": 2})
    history.add({"n": 3})
    assert [item["n"] for item in history.snapshot()] == [2, 3]
    history.clear()
    assert history.snapshot() == []


def test_overlarge_body_is_rejected() -> None:
    """На тело больше лимита — 413: гигабайт не читается в память."""
    with _SinkApp() as sink:
        too_big = b"x" * (MAX_BODY_BYTES + 1)
        status, body = _request(sink, "POST", "/webhook", too_big)
        assert status == 413
        assert "байт" in body["error"]


def test_summarize_selects_safe_fields() -> None:
    """В запись попадают только `LOGGED_FIELDS`, недостающие — `-`."""
    record = summarize_alert({})
    assert set(record) == {"status", "alertname", "severity", "summary"}
    assert record["alertname"] == "-"
    assert format_alert(record) == "[-] - (severity=-): -"
