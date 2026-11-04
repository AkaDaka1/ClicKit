"""Корреляция запросов ClicKit Cloud: `X-Request-ID` и журнальный контекст.

Контракт — `docs/api.md` §3: валидный входящий `X-Request-ID`
(32–64 символа `[A-Za-z0-9._-]`) пробрасывается, иначе сервер генерирует
UUID4; заголовок возвращается **на всех** ответах (успешных и ошибочных),
а `.request_id` попадает в problem+json. Тот же идентификатор кладётся в
`ContextVar`, поэтому каждая запись журнала внутри обработки запроса
помечается им (полноценные трейсы — M8).
"""

from __future__ import annotations

import logging
import re
import time
import uuid
from contextvars import ContextVar
from typing import Any

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

#: Заголовок корреляции (`docs/api.md` §3).
REQUEST_ID_HEADER = "X-Request-ID"
#: Минимальная длина валидного входящего идентификатора.
MIN_REQUEST_ID_LENGTH = 32
#: Максимальная длина валидного входящего идентификатора.
MAX_REQUEST_ID_LENGTH = 64
#: Формат журнала сервиса: идентификатор запроса виден в каждой строке.
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s [%(request_id)s]: %(message)s"

_REQUEST_ID_RE = re.compile(r"[A-Za-z0-9._-]+")

#: Идентификатор текущего запроса для фильтра журнала (вне запроса — `None`).
current_request_id: ContextVar[str | None] = ContextVar(
    "clikit_request_id", default=None
)

logger = logging.getLogger(__name__)


def is_valid_request_id(value: str | None) -> bool:
    """Проверить входящий `X-Request-ID` по правилам контракта.

    Args:
        value: Значение заголовка (может быть `None`).

    Returns:
        `True`, если длина 32–64 символа и алфавит `[A-Za-z0-9._-]`.
    """
    if value is None:
        return False
    if not MIN_REQUEST_ID_LENGTH <= len(value) <= MAX_REQUEST_ID_LENGTH:
        return False
    return _REQUEST_ID_RE.fullmatch(value) is not None


def sanitize_request_id(raw: str | None) -> str:
    """Вернуть валидный идентификатор: входящий или свежий UUID4.

    Args:
        raw: Входящий заголовок `X-Request-ID` или `None`.

    Returns:
        Валидный идентификатор для ответа и журнала.
    """
    candidate = raw.strip() if isinstance(raw, str) else None
    if candidate and is_valid_request_id(candidate):
        return candidate
    return str(uuid.uuid4())


def request_id_of_scope(scope: Scope) -> str:
    """Идентификатор запроса из ASGI-scope (или свежий UUID4).

    Используется слоями, которые отвечают до/вне FastAPI-обработчиков
    (например, лимит тела), чтобы ответ всё равно содержал корреляцию.

    Args:
        scope: ASGI-scope запроса.

    Returns:
        Идентификатор, уже сохранённый middleware, иначе новый UUID4.
    """
    state = scope.get("state") or {}
    existing = state.get("request_id")
    if isinstance(existing, str) and existing:
        return existing
    return str(uuid.uuid4())


class RequestIdFilter(logging.Filter):
    """Добавить `request_id` в запись журнала (вне запроса — `"-"`)."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Проставить атрибут и пропустить запись дальше.

        Args:
            record: Запись журнала.

        Returns:
            Всегда `True`: фильтр только обогащает запись.
        """
        record.request_id = current_request_id.get() or "-"
        return True


class RequestContextMiddleware:
    """Присвоить запросу `X-Request-ID` и вернуть его в ответе.

    Middleware ставится внешним слоем пользовательских middleware, поэтому
    идентификатор есть и у ответов `BodySizeLimitMiddleware` (413), и у
    успешных ответов. Ошибки, которые обрабатывает `ServerErrorMiddleware`
    (500), формируются вне этого слоя, но берут идентификатор из
    `scope["state"]` — он общий с `request.state`.
    """

    def __init__(self, app: ASGIApp) -> None:
        """Обернуть ASGI-приложение.

        Args:
            app: Следующий слой стека Starlette.
        """
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Обработать HTTP-запрос, проставив идентификатор и запись журнала."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = sanitize_request_id(Headers(scope=scope).get(REQUEST_ID_HEADER))
        state: dict[str, Any] = scope.setdefault("state", {})
        state["request_id"] = request_id
        token = current_request_id.set(request_id)
        started = time.perf_counter()
        status_code = 500

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            elapsed_ms = (time.perf_counter() - started) * 1000
            logger.info(
                "[%s] %s %s -> %s за %.1f мс",
                request_id,
                scope.get("method", "-"),
                scope.get("path", "/"),
                status_code,
                elapsed_ms,
            )
            current_request_id.reset(token)


def configure_logging(level: str) -> None:
    """Настроить журнал сервиса с идентификатором запроса.

    Повторный вызов не дублирует обработчики и фильтры: `basicConfig` не
    трогает уже настроенный журнал, а фильтр добавляется по типу. Чужие
    обработчики (например, pytest) не переформатируются.

    Args:
        level: Уровень журнала из `CLICKIT_LOG_LEVEL`.
    """
    logging.basicConfig(level=level, format=LOG_FORMAT)
    for handler in logging.getLogger().handlers:
        if not any(isinstance(item, RequestIdFilter) for item in handler.filters):
            handler.addFilter(RequestIdFilter())
