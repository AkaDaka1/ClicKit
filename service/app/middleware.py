"""Общий слой ограничения размера тела запроса (`docs/api.md` §6).

Лимит проверяется **до** разбора JSON и до записи в БД, поэтому реализован
как ASGI-middleware, а не внутри отдельных маршрутов: один и тот же предел
действует и для публикации сценария, и для crash-отчёта. Запрос без
`Content-Length` читается потоково с потолком — память не расходуется на
заведомо слишком большое тело.
"""

from __future__ import annotations

from typing import Any

from starlette.datastructures import Headers
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from service.app.config import DEFAULT_MAX_BODY_BYTES
from service.app.errors import problem_response
from service.app.request_id import request_id_of_scope


class BodySizeLimitMiddleware:
    """Отклонять запросы, тело которых больше `CLICKIT_MAX_BODY_BYTES`."""

    def __init__(self, app: ASGIApp) -> None:
        """Обернуть ASGI-приложение.

        Args:
            app: Следующий слой стека Starlette.
        """
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Проверить размер тела и передать запрос дальше либо ответить 413."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        limit = self._limit(scope)
        declared = Headers(scope=scope).get("content-length")
        if declared is not None and declared.isdigit() and int(declared) > limit:
            await self._reject(scope, receive, send, limit)
            return

        body, oversized = await _read_capped(receive, limit)
        if oversized:
            await self._reject(scope, receive, send, limit)
            return
        await self.app(scope, _replay(body, receive), send)

    @staticmethod
    def _limit(scope: Scope) -> int:
        """Предел тела из настроек приложения (или значение по умолчанию)."""
        app = scope.get("app")
        settings = getattr(getattr(app, "state", None), "settings", None)
        max_bytes = getattr(settings, "max_body_bytes", None)
        return max_bytes if isinstance(max_bytes, int) else DEFAULT_MAX_BODY_BYTES

    @staticmethod
    async def _reject(scope: Scope, receive: Receive, send: Send, limit: int) -> None:
        """Ответить 413 в формате problem+json, не читая тело дальше."""
        response = problem_response(
            413,
            "payload-too-large",
            f"Тело запроса больше лимита {limit} байт",
            instance=scope.get("path", "/"),
            request_id=request_id_of_scope(scope),
        )
        await response(scope, receive, send)


async def _read_capped(receive: Receive, limit: int) -> tuple[bytes, bool]:
    """Прочитать тело с потолком; второй элемент — «превышен ли лимит»."""
    chunks: list[bytes] = []
    total = 0
    while True:
        message: Message = await receive()
        if message["type"] == "http.disconnect":
            return b"".join(chunks), False
        chunk = message.get("body", b"")
        total += len(chunk)
        if total > limit:
            return b"", True
        chunks.append(chunk)
        if not message.get("more_body", False):
            return b"".join(chunks), False


def _replay(body: bytes, receive: Receive) -> Receive:
    """Приёмник, который сначала отдаёт прочитанное тело, затем — оригинал."""
    state: dict[str, Any] = {"sent": False}

    async def replay() -> Message:
        if not state["sent"]:
            state["sent"] = True
            return {"type": "http.request", "body": body, "more_body": False}
        return await receive()

    return replay
