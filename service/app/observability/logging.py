"""JSON-журнал сервиса ClicKit Cloud (M8 T1.1).

Контракт журнала — `plans/M8-observability.md` §4.1: каждая запись — одна
JSON-строка в stdout с обязательными полями `timestamp`, `level`, `logger`,
`message`, `service`, `version`, `request_id`, `trace_id`. Идентификаторы
берутся из `ContextVar` (`request_id` — `service/app/request_id.py`,
`trace_id` — заполнит OTel в T1.3), поэтому одна строка журнала связывает
HTTP-запрос, лог и будущий трейс (ADR №41).

Секреты не попадают в журнал двумя способами: значения API-ключей
передаются в `configure_logging` и заменяются на `***`, а типовые пары
`X-API-Key: …`/`password=…` вырезаются регуляркой. Текст исключений
дополнительно проходит санитайзер PII из `crash_service` (домашние каталоги
→ `<пользователь>`), поэтому traceback в журнале не раскрывает пути
пользователя.
"""

from __future__ import annotations

import json
import logging
import re
import sys
import traceback
from collections.abc import Iterable
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any, TextIO

from service.app.crash_service import sanitize_traceback
from service.app.request_id import current_request_id
from service.app.version import SERVICE_NAME, SERVICE_VERSION

#: Обязательные поля каждой записи журнала (контракт M8 §4.1).
REQUIRED_FIELDS: tuple[str, ...] = (
    "timestamp",
    "level",
    "logger",
    "message",
    "service",
    "version",
    "request_id",
    "trace_id",
)
#: Необязательные структурированные поля: попадают в JSON, только если заданы.
EXTRA_FIELDS: tuple[str, ...] = (
    "event",
    "method",
    "path",
    "route",
    "status",
    "duration_ms",
    "error_type",
)
#: Значение отсутствующего идентификатора (вне запроса/трейса).
MISSING = "-"
#: Маркер «наш» обработчик, чтобы не трогать чужие (например, pytest).
_HANDLER_MARK = "_clikit_json_handler"
#: Имена логгеров uvicorn, которые переводим на общий JSON-обработчик.
_UVICORN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")
#: Пары «имя секрета = значение», которые нельзя писать в журнал.
_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"(?i)\b(x-api-key|api[_-]?key|authorization|password|secret)\b"
        r"\s*[:=]\s*\S+"
    ),
)

#: Идентификатор текущего трейса (заполняется OTel в T1.3; вне трейса — `None`).
current_trace_id: ContextVar[str | None] = ContextVar("clikit_trace_id", default=None)


def _timestamp(created: float) -> str:
    """Время записи в ISO 8601 UTC с миллисекундами (`2026-11-13T10:00:00.000Z`)."""
    moment = datetime.fromtimestamp(created, tz=UTC)
    return moment.isoformat(timespec="milliseconds").replace("+00:00", "Z")


class JsonFormatter(logging.Formatter):
    """Форматтер одной JSON-строки на запись журнала.

    Attributes:
        secrets: Значения, которые заменяются на `***` в сообщении и traceback.
    """

    def __init__(self, secrets: Iterable[str] = ()) -> None:
        """Запомнить секреты, подлежащие маскировке.

        Args:
            secrets: Значения API-ключей и других секретов (пустые
                игнорируются).
        """
        super().__init__()
        self.secrets = tuple(item for item in secrets if item)

    def format(self, record: logging.LogRecord) -> str:
        """Собрать запись журнала в виде JSON-строки.

        Args:
            record: Запись стандартного `logging`.

        Returns:
            Одна строка JSON без переводов строк (UTF-8-безопасная).
        """
        payload: dict[str, Any] = {
            "timestamp": _timestamp(record.created),
            "level": record.levelname,
            "logger": record.name,
            "message": self._redact(record.getMessage()),
            "service": SERVICE_NAME,
            "version": SERVICE_VERSION,
            "request_id": getattr(record, "request_id", None) or MISSING,
            "trace_id": getattr(record, "trace_id", None) or MISSING,
        }
        for name in EXTRA_FIELDS:
            value = getattr(record, name, None)
            if value is not None:
                payload[name] = value
        if record.exc_info:
            payload["exception"] = self._redact(
                "".join(traceback.format_exception(*record.exc_info)).rstrip()
            )
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    def _redact(self, text: str) -> str:
        """Убрать секреты и PII из текста сообщения или traceback.

        Args:
            text: Исходный текст.

        Returns:
            Текст без значений секретов и домашних каталогов.
        """
        cleaned = text
        for secret in self.secrets:
            cleaned = cleaned.replace(secret, "***")
        for pattern in _SECRET_PATTERNS:
            cleaned = pattern.sub(lambda match: f"{match.group(1)}=***", cleaned)
        return sanitize_traceback(cleaned)


class CorrelationFilter(logging.Filter):
    """Добавить `request_id` и `trace_id` в каждую запись журнала."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Проставить атрибуты корреляции и пропустить запись дальше.

        Args:
            record: Запись журнала.

        Returns:
            Всегда `True`: фильтр только обогащает запись.
        """
        record.request_id = (
            getattr(record, "request_id", None) or current_request_id.get() or MISSING
        )
        record.trace_id = (
            getattr(record, "trace_id", None) or current_trace_id.get() or MISSING
        )
        return True


def configure_logging(
    level: str,
    *,
    secrets: Iterable[str] = (),
    stream: TextIO | None = None,
) -> None:
    """Настроить JSON-журнал сервиса в stdout.

    Повторный вызов заменяет только обработчик ClicKit, не затрагивая чужие
    (pytest, uvicorn до старта приложения). Логгеры uvicorn переводятся на
    общий обработчик, чтобы access-строки тоже были JSON.

    Args:
        level: Уровень журнала из `CLICKIT_LOG_LEVEL`.
        secrets: Значения секретов для маскировки (API-ключи).
        stream: Поток вывода (тесты); по умолчанию `sys.stdout` на момент
            **каждой записи** — так работают и захват pytest (`capsys`),
            и журнал контейнера (stdout), даже если обработчик создан раньше.
            При `None` поток дополнительно переводится в UTF-8, чтобы JSON
            не зависел от кодировки локали (локальный запуск на Windows).
    """
    root = logging.getLogger()
    root.setLevel(level)
    for handler in list(root.handlers):
        if getattr(handler, _HANDLER_MARK, False):
            root.removeHandler(handler)
            handler.close()

    handler = _LateBoundStreamHandler(stream)
    handler.setFormatter(JsonFormatter(secrets))
    handler.addFilter(CorrelationFilter())
    setattr(handler, _HANDLER_MARK, True)
    root.addHandler(handler)
    _ensure_utf8_stream(stream)
    _adopt_uvicorn_loggers()


def _ensure_utf8_stream(stream: TextIO | None) -> None:
    """Перевести поток журнала в UTF-8, чтобы JSON не бился о кодировку локали.

    В Linux-контейнере stdout и так UTF-8, но при запуске на Windows (локальная
    отладка) локали по умолчанию пишут JSON в cp1251 — такие строки не
    распарсит ни Promtail, ни человек. `reconfigure` доступен у текстовых
    потоков Python 3.7+; для подменённых тестами объектов его может не быть.

    Args:
        stream: Явно заданный поток (тесты) — не трогаем; `None` — `sys.stdout`
            в момент записи (в том числе подменённый после настройки).
    """
    if stream is not None:
        return
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is None:
        return
    try:
        reconfigure(encoding="utf-8", errors="replace")
    except (OSError, ValueError):  # pragma: no cover — поток уже закрыт
        pass


class _LateBoundStreamHandler(logging.StreamHandler):
    """Обработчик, который берёт поток при каждой записи.

    `logging.StreamHandler` фиксирует поток в конструкторе, поэтому порядок
    «настройка журнала → подмена `sys.stdout`» (оркестратор, pytest)
    отправлял записи в старый объект. Здесь поток разрешается заново.
    """

    def __init__(self, stream: TextIO | None = None) -> None:
        """Создать обработчик без заранее зафиксированного потока.

        Args:
            stream: Постоянный поток (тесты) или `None` — `sys.stdout`.
        """
        super().__init__(stream)
        self._fixed_stream = stream

    @property
    def stream(self) -> TextIO:  # type: ignore[override]
        """Поток вывода: заданный явно или текущий `sys.stdout`."""
        if self._fixed_stream is not None:
            return self._fixed_stream
        return sys.stdout

    @stream.setter
    def stream(self, value: TextIO) -> None:
        self._fixed_stream = value


def _adopt_uvicorn_loggers() -> None:
    """Перевести логгеры uvicorn на общий JSON-обработчик.

    uvicorn по умолчанию ставит собственные обработчики с `propagate=False`,
    поэтому без этого шага access-логи остались бы текстовыми и без
    `request_id`.
    """
    for name in _UVICORN_LOGGERS:
        uvicorn_logger = logging.getLogger(name)
        for handler in list(uvicorn_logger.handlers):
            uvicorn_logger.removeHandler(handler)
        uvicorn_logger.propagate = True
