"""Локальный приёмник вебхуков Alertmanager (M8 T2.1).

Зачем: локальный стек наблюдаемости должен кому-то «доставлять» алерты,
чтобы их можно было увидеть, проверить и показать в демо (T3.1, T5.1).
Почта, Telegram и PagerDuty для пет-проекта — лишние зависимости и секреты,
поэтому приёмник — маленький HTTP-сервер на стандартной библиотеке:

* `POST /webhook` принимает JSON Alertmanager v4 (поле `alerts`) и печатает
  одну строку на алерт: статус, имя, severity, summary;
* `GET /alerts` отдаёт JSON — последние `--history` алертов, удобно в
  PowerShell/браузере;
* `GET /healthz` — liveness для compose healthcheck.

В журнал пишутся только поля `status`, `alertname`, `severity`, `summary`:
аннотации и метки алертов могут содержать что угодно, а приёмник не должен
становиться местом утечки (ADR №41, №64). Тело запроса больше
`MAX_BODY_BYTES` не читается.

Запуск (локально или в контейнере):

    python scripts/alert_sink.py --port 8080
    curl.exe -s http://localhost:8080/alerts

Контракт интеграции: `observability/alertmanager/alertmanager.yml`
(`webhook_configs[].url` → `http://alert-sink:8080/webhook`).
"""

from __future__ import annotations

import argparse
import json
import threading
from collections import deque
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

#: Порт по умолчанию; хост-порт задаётся `CLICKIT_ALERT_SINK_PORT` в compose.
DEFAULT_PORT = 8080
#: Сколько последних записей хранить для `GET /alerts`.
DEFAULT_HISTORY = 100
#: Лимит тела: вебхук Alertmanager не бывает большим, больше — ошибка клиента.
MAX_BODY_BYTES = 1_048_576
#: Сколько байт «переразмеренного» тела прочитать и отбросить перед ответом 413.
#: Если просто закрыть сокет с непрочитанными данными, TCP пришлёт RST и
#: клиент увидит обрыв соединения вместо внятной ошибки (наблюдалось на Windows).
MAX_DRAIN_BYTES = 4 * MAX_BODY_BYTES
#: Размер блока при сливе тела: не держим мегабайты в памяти одним куском.
DRAIN_CHUNK_BYTES = 65_536
#: Поля алерта, которые попадают в журнал. Всё остальное — только в памяти.
LOGGED_FIELDS = ("status", "alertname", "severity", "summary")


def _now() -> str:
    """Текущее время в ISO-8601 UTC — единый формат для записей приёмника."""
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def summarize_alert(alert: dict[str, Any]) -> dict[str, str]:
    """Выбрать безопасные поля алерта для журнала и `GET /alerts`.

    Args:
        alert: Элемент `alerts` из вебхука Alertmanager v4.

    Returns:
        Словарь `status`, `alertname`, `severity`, `summary`; недостающие
        значения — пустая строка, чтобы формат строки не зависел от данных.
    """
    labels = alert.get("labels") or {}
    annotations = alert.get("annotations") or {}
    status = alert.get("status") or "-"
    values = {
        "status": str(status),
        "alertname": str(labels.get("alertname") or "-"),
        "severity": str(labels.get("severity") or "-"),
        "summary": str(annotations.get("summary") or "-"),
    }
    return {key: values[key] for key in LOGGED_FIELDS}


def format_alert(record: dict[str, str]) -> str:
    """Однострочное представление алерта для stdout контейнера приёмника."""
    return (
        f"[{record['status']}] {record['alertname']}"
        f" (severity={record['severity']}): {record['summary']}"
    )


class AlertHistory:
    """Потокобезопасная история принятых алертов (ограниченная длина)."""

    def __init__(self, limit: int = DEFAULT_HISTORY) -> None:
        """Создать буфер последних алертов.

        Args:
            limit: Максимум хранимых записей; старые вытесняются.
        """
        if limit <= 0:
            raise ValueError("limit должен быть больше нуля")
        self._items: deque[dict[str, Any]] = deque(maxlen=limit)
        self._lock = threading.Lock()

    def add(self, item: dict[str, Any]) -> None:
        """Добавить запись и вытеснить самую старую при переполнении."""
        with self._lock:
            self._items.append(item)

    def snapshot(self) -> list[dict[str, Any]]:
        """Вернуть копию истории в порядке поступления."""
        with self._lock:
            return list(self._items)

    def clear(self) -> None:
        """Очистить историю (тесты)."""
        with self._lock:
            self._items.clear()


class AlertSinkHandler(BaseHTTPRequestHandler):
    """HTTP-обработчик приёмника: `POST /webhook`, `GET /alerts`, `GET /healthz`."""

    #: Заполняется фабрикой `make_server` — берётся из `server.history`.
    server_version = "ClicKitAlertSink/1.0"
    #: Шумный access-log стандартного `HTTPServer` не нужен: записи даёт вебхук.
    quiet = True

    @property
    def history(self) -> AlertHistory:
        """История алертов, прикреплённая к серверу."""
        return self.server.history  # type: ignore[attr-defined]

    def log_message(self, format: str, *args: Any) -> None:
        """Подавить стандартный access-log (формат журнала — наши записи)."""
        if not self.quiet:
            super().log_message(format, *args)

    def do_GET(self) -> None:  # noqa: N802 — имя задаёт `BaseHTTPRequestHandler`
        """`/healthz` — 200; `/alerts` — JSON истории; прочее — 404."""
        if self.path.split("?", 1)[0] == "/healthz":
            self._send_json(HTTPStatus.OK, {"status": "ok"})
        elif self.path.split("?", 1)[0] == "/alerts":
            self._send_json(HTTPStatus.OK, {"alerts": self.history.snapshot()})
        else:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802 — имя задаёт `BaseHTTPRequestHandler`
        """Принять вебхук Alertmanager v4 на `/webhook`."""
        if self.path.split("?", 1)[0] != "/webhook":
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        payload = self._read_json_body()
        if payload is None:
            return
        alerts = payload.get("alerts")
        if not isinstance(alerts, list):
            self._send_json(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                {"error": "ожидается поле alerts: [..] (формат Alertmanager v4)"},
            )
            return
        received_at = _now()
        records = [
            summarize_alert(alert) for alert in alerts if isinstance(alert, dict)
        ]
        for record in records:
            self.history.add({**record, "received_at": received_at})
            print(format_alert(record), flush=True)
        self._send_json(HTTPStatus.OK, {"received": len(records)})

    def _read_json_body(self) -> dict[str, Any] | None:
        """Прочитать JSON-тело с лимитом; на ошибке уже отправить ответ."""
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            self._send_json(
                HTTPStatus.BAD_REQUEST, {"error": "некорректный Content-Length"}
            )
            return None
        if length > MAX_BODY_BYTES:
            self._drain_body(length)
            self._send_json(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                {"error": f"тело больше {MAX_BODY_BYTES} байт"},
            )
            return None
        raw = self.rfile.read(length) if length > 0 else b""
        try:
            payload = json.loads(raw.decode("utf-8") or "null")
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "ожидается JSON"})
            return None
        if not isinstance(payload, dict):
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "ожидается JSON-объект"})
            return None
        return payload

    def _drain_body(self, length: int) -> None:
        """Прочитать и отбросить тело, чтобы клиент получил ответ, а не RST.

        Читаем не больше `MAX_DRAIN_BYTES`: защита от бесконечного потока.
        Если тело не дочитано, соединение закроется — это лучше, чем держать
        поток в памяти.
        """
        remaining = min(length, MAX_DRAIN_BYTES)
        while remaining > 0:
            chunk = self.rfile.read(min(remaining, DRAIN_CHUNK_BYTES))
            if not chunk:
                break
            remaining -= len(chunk)

    def _send_json(self, status: HTTPStatus, payload: Any) -> None:
        """Отправить JSON-ответ с корректной длиной и кодировкой."""
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def make_server(
    host: str = "0.0.0.0",  # noqa: S104 — контейнер должен слушать все интерфейсы
    port: int = DEFAULT_PORT,
    history: AlertHistory | None = None,
) -> ThreadingHTTPServer:
    """Собрать HTTP-сервер приёмника (без запуска).

    Args:
        host: Адрес прослушивания.
        port: Порт; `0` — свободный (тесты).
        history: Готовая история; `None` — новая с лимитом по умолчанию.

    Returns:
        Готовый `ThreadingHTTPServer` с прикреплённой историей.
    """
    server = ThreadingHTTPServer((host, port), AlertSinkHandler)
    server.daemon_threads = True
    server.history = history if history is not None else AlertHistory()  # type: ignore[attr-defined]
    return server


def main(argv: list[str] | None = None) -> int:
    """Точка входа скрипта: `python scripts/alert_sink.py --port 8080`."""
    parser = argparse.ArgumentParser(description="Приёмник вебхуков Alertmanager")
    parser.add_argument("--host", default="0.0.0.0", help="адрес прослушивания")
    parser.add_argument(
        "--port", type=int, default=DEFAULT_PORT, help="порт (по умолчанию 8080)"
    )
    parser.add_argument(
        "--history",
        type=int,
        default=DEFAULT_HISTORY,
        help=f"сколько последних алертов хранить (по умолчанию {DEFAULT_HISTORY})",
    )
    args = parser.parse_args(argv)

    server = make_server(args.host, args.port, AlertHistory(args.history))
    print(
        f"alert-sink слушает http://{args.host}:{server.server_address[1]} "
        f"(вебхук /webhook, история /alerts)",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
