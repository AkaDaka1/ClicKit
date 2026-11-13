"""Тесты JSON-журнала сервиса (M8 T1.1).

Проверяется контракт `plans/M8-observability.md` §4.1: каждая запись —
одна JSON-строка с обязательными полями; `request_id` совпадает с заголовком
ответа; `trace_id` присутствует (в T1.3 его заполнит OTel); секреты, пары
`X-API-Key: …`/`password=…` и домашние каталоги в traceback не попадают в
журнал; логгеры uvicorn переводятся на общий обработчик.
"""

from __future__ import annotations

import io
import json
import logging
import sys

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("sqlalchemy")

from fastapi.testclient import TestClient  # noqa: E402

from service.app.observability.logging import (  # noqa: E402
    REQUIRED_FIELDS,
    JsonFormatter,
    configure_logging,
    current_trace_id,
)
from service.app.request_id import current_request_id  # noqa: E402
from tests.service.conftest import API_KEY  # noqa: E402

VALID_ID = "client-request-id-0123456789abcdef"
#: Пометка нашего обработчика (как в `service.app.observability.logging`).
HANDLER_MARK = "_clikit_json_handler"


def _is_ours(handler: logging.Handler) -> bool:
    """Наш ли это JSON-обработчик (в сравнении с pytest/caplog)."""
    return bool(getattr(handler, HANDLER_MARK, False))


def _restore_root(
    root: logging.Logger,
    saved_handlers: list[logging.Handler],
    saved_level: int,
) -> None:
    """Вернуть корневой журнал в состояние до `configure_logging`."""
    for handler in list(root.handlers):
        if _is_ours(handler):
            root.removeHandler(handler)
            handler.close()
    for handler in saved_handlers:
        if handler not in root.handlers:
            root.addHandler(handler)
    root.setLevel(saved_level)


def _make_record(
    message: str = "проверка",
    *,
    exc_info: tuple[object, ...] | None = None,
) -> logging.LogRecord:
    """Собрать запись журнала, как её создаёт стандартный `logging`."""
    record = logging.LogRecord(
        name="service.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=(),
        exc_info=None,
    )
    # `LogRecord` приводится `exc_info` к кортежу в конструкторе и теряет
    # ссылку на исключение — ставим его явно, как это делает `logger.exception`.
    record.exc_info = exc_info
    return record


def test_every_line_is_json_with_required_fields() -> None:
    """Запись — одна JSON-строка с обязательными полями (контракт §4.1)."""
    formatter = JsonFormatter()
    record = _make_record("Привет, мир")
    record.request_id = VALID_ID
    record.trace_id = "0123456789abcdef0123456789abcdef"

    line = formatter.format(record)
    payload = json.loads(line)

    assert "\n" not in line
    assert tuple(payload)[: len(REQUIRED_FIELDS)] == REQUIRED_FIELDS
    assert payload["message"] == "Привет, мир"
    assert payload["level"] == "INFO"
    assert payload["logger"] == "service.test"
    assert payload["service"] == "clikit-cloud"
    assert payload["version"]
    assert payload["request_id"] == VALID_ID
    assert payload["trace_id"] == "0123456789abcdef0123456789abcdef"
    assert payload["timestamp"].endswith("Z")


def test_missing_correlation_fields_are_dashes() -> None:
    """Вне запроса и трейса поля не исчезают, а содержат `-`."""
    payload = json.loads(JsonFormatter().format(_make_record()))

    assert payload["request_id"] == "-"
    assert payload["trace_id"] == "-"
    assert "event" not in payload, "пустые необязательные поля не пишутся"


def test_secret_values_are_masked() -> None:
    """Значение API-ключа никогда не попадает в запись журнала."""
    formatter = JsonFormatter(secrets=[API_KEY])

    payload = json.loads(formatter.format(_make_record(f"ключ {API_KEY}")))

    assert API_KEY not in json.dumps(payload, ensure_ascii=False)
    assert "***" in payload["message"]


def test_key_value_pairs_are_redacted() -> None:
    """Типовые пары «заголовок/пароль = значение» вырезаются регуляркой."""
    formatter = JsonFormatter()
    message = "X-API-Key: supersecretvalue password=hunter2 ok"

    payload = json.loads(formatter.format(_make_record(message)))

    assert "supersecretvalue" not in payload["message"]
    assert "hunter2" not in payload["message"]
    assert payload["message"].endswith("ok")


def test_traceback_is_sanitized() -> None:
    """Traceback в журнале есть, но домашние каталоги заменены (PII)."""
    try:
        raise RuntimeError(r"не удалось открыть C:\Users\Daka\secret.txt")
    except RuntimeError:
        record = _make_record("Ошибка", exc_info=sys.exc_info())
        payload = json.loads(JsonFormatter().format(record))

    assert "RuntimeError" in payload["exception"]
    assert "Daka" not in payload["exception"]
    assert "<пользователь>" in payload["exception"]


def test_configure_logging_writes_context_vars() -> None:
    """Настроенный обработчик пишет JSON с `request_id` из контекста запроса."""
    # Изоляция: сохраняем и восстанавливаем корневой журнал после теста.
    root = logging.getLogger()
    saved_handlers = list(root.handlers)
    saved_level = root.level
    stream = io.StringIO()
    try:
        configure_logging("INFO", stream=stream)  # type: ignore[arg-type]
        token = current_request_id.set(VALID_ID)
        trace_token = current_trace_id.set("trace-1")
        try:
            logging.getLogger("service.test").info("внутри запроса")
        finally:
            current_request_id.reset(token)
            current_trace_id.reset(trace_token)
        logging.getLogger("service.test").info("вне запроса")
    finally:
        _restore_root(root, saved_handlers, saved_level)

    lines = [json.loads(item) for item in stream.getvalue().splitlines()]
    assert [item["message"] for item in lines] == ["внутри запроса", "вне запроса"]
    assert lines[0]["request_id"] == VALID_ID
    assert lines[0]["trace_id"] == "trace-1"
    assert lines[1]["request_id"] == "-"
    assert lines[1]["trace_id"] == "-"


def test_repeated_configure_does_not_duplicate_handlers() -> None:
    """Повторная настройка заменяет наш обработчик, а не добавляет второй."""
    root = logging.getLogger()
    saved_handlers = list(root.handlers)
    saved_level = root.level
    try:
        configure_logging("INFO", stream=io.StringIO())  # type: ignore[arg-type]
        configure_logging("INFO", stream=io.StringIO())  # type: ignore[arg-type]
        ours = [handler for handler in root.handlers if _is_ours(handler)]
    finally:
        _restore_root(root, saved_handlers, saved_level)

    assert len(ours) == 1


def test_uvicorn_loggers_propagate_to_root() -> None:
    """Access-логи uvicorn идут через общий JSON-обработчик."""
    root = logging.getLogger()
    saved_handlers = list(root.handlers)
    saved_level = root.level
    uvicorn_logger = logging.getLogger("uvicorn.access")
    saved_uvicorn_handlers = list(uvicorn_logger.handlers)
    saved_propagate = uvicorn_logger.propagate
    try:
        configure_logging("INFO", stream=io.StringIO())  # type: ignore[arg-type]
        assert uvicorn_logger.handlers == []
        assert uvicorn_logger.propagate is True
    finally:
        uvicorn_logger.handlers = saved_uvicorn_handlers
        uvicorn_logger.propagate = saved_propagate
        _restore_root(root, saved_handlers, saved_level)


def test_configure_logging_switches_stdout_to_utf8(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """stdout переводится в UTF-8 — JSON не зависит от кодировки локали."""
    calls: list[dict[str, object]] = []

    def fake_reconfigure(**kwargs: object) -> None:
        calls.append(kwargs)

    monkeypatch.setattr(
        sys,
        "stdout",
        type("S", (), {"reconfigure": staticmethod(fake_reconfigure)})(),
    )
    root = logging.getLogger()
    saved_handlers = list(root.handlers)
    saved_level = root.level
    try:
        configure_logging("INFO")
    finally:
        _restore_root(root, saved_handlers, saved_level)

    assert calls == [{"encoding": "utf-8", "errors": "replace"}]


def test_application_writes_json_access_log(
    client: TestClient, capsys: pytest.CaptureFixture[str]
) -> None:
    """Сквозной путь: запрос к приложению оставляет JSON-строку с `request_id`."""
    capsys.readouterr()  # отбросить записи старта приложения
    client.get("/version", headers={"X-Request-ID": VALID_ID})

    captured = capsys.readouterr()
    payloads = [json.loads(line) for line in captured.out.splitlines() if line]
    access = [item for item in payloads if item.get("event") == "http_request"]

    assert access, f"нет JSON access-записи: {captured.out!r}"
    entry = access[-1]
    assert set(REQUIRED_FIELDS) <= set(entry)
    assert entry["request_id"] == VALID_ID
    assert entry["method"] == "GET"
    assert entry["path"] == "/version"
    assert entry["status"] == 200
    assert API_KEY not in captured.out


def test_api_key_never_appears_in_logs(
    client: TestClient, capsys: pytest.CaptureFixture[str]
) -> None:
    """Ключ из настроек маскируется, даже если попал в текст сообщения (T3.1)."""
    logging.getLogger("service.test").warning("ключ настроек %s", API_KEY)

    out = capsys.readouterr().out
    assert out, "журнал пуст — JSON-обработчик не подключён"
    assert API_KEY not in out
    assert "***" in out
