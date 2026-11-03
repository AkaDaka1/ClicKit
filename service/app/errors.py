"""Ошибки API ClicKit Cloud в формате RFC 7807 (`application/problem+json`).

Единая точка формирования ответов об ошибках: контракт `docs/api.md` §4
описывает поля `type`, `title`, `status`, `detail`, `instance`, `request_id`
и необязательный список `errors` (пути валидации, до 50 записей). Модуль
намеренно не импортирует FastAPI-специфику ответа — это обычный `JSONResponse`,
поэтому обработчики можно регистрировать и без запуска приложения.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

#: Базовый префикс стабильных URN-типов ошибок (`docs/api.md` §4).
TYPE_PREFIX = "urn:clikit:error:"
#: Content-Type ошибок по RFC 7807.
PROBLEM_MEDIA_TYPE = "application/problem+json"
#: Максимум записей в списке `errors` (совпадает с лимитом IR).
MAX_ERRORS = 50

#: Код ошибки → (URN-тип, короткий заголовок). Заголовки совпадают с §4.
CATALOG: dict[str, tuple[str, str]] = {
    "unauthorized": (f"{TYPE_PREFIX}unauthorized", "Требуется API-ключ"),
    "forbidden": (f"{TYPE_PREFIX}forbidden", "Недостаточно прав"),
    "not-found": (f"{TYPE_PREFIX}not-found", "Сценарий не найден"),
    "conflict": (f"{TYPE_PREFIX}conflict", "Конфликт идемпотентности"),
    "payload-too-large": (
        f"{TYPE_PREFIX}payload-too-large",
        "Тело запроса слишком большое",
    ),
    "unsupported-media-type": (
        f"{TYPE_PREFIX}unsupported-media-type",
        "Неподдерживаемый тип содержимого",
    ),
    "validation": (f"{TYPE_PREFIX}validation", "Запрос не прошёл проверку"),
    "unavailable": (f"{TYPE_PREFIX}unavailable", "Сервис недоступен"),
    "internal": (f"{TYPE_PREFIX}internal", "Внутренняя ошибка сервиса"),
}


class ApiError(Exception):
    """Ошибка API с HTTP-кодом, кодом каталога и опциональными путями.

    Attributes:
        status_code: HTTP-код ответа (401, 404, 422, …).
        code: Ключ каталога `CATALOG` (например, `validation`).
        detail: Человекочитаемая деталь ответа.
        issues: Список `{path, message}` для 422 (не больше `MAX_ERRORS`).
    """

    def __init__(
        self,
        status_code: int,
        code: str,
        detail: str,
        *,
        issues: list[dict[str, str]] | None = None,
    ) -> None:
        """Создать ошибку API.

        Args:
            status_code: HTTP-код ответа.
            code: Ключ каталога типов ошибок.
            detail: Пояснение для клиента.
            issues: Ошибки валидации (только для 422).
        """
        super().__init__(detail)
        self.status_code = status_code
        self.code = code
        self.detail = detail
        self.issues = issues

    def to_problem(
        self,
        *,
        instance: str,
        request_id: str,
    ) -> dict[str, Any]:
        """Собрать тело problem+json.

        Args:
            instance: Путь запроса (`request.url.path`).
            request_id: Идентификатор корреляции (`X-Request-ID`).

        Returns:
            Словарь полей RFC 7807, готовый к отправке клиенту.
        """
        urn, title = CATALOG.get(self.code, CATALOG["internal"])
        body: dict[str, Any] = {
            "type": urn,
            "title": title,
            "status": self.status_code,
            "detail": self.detail,
            "instance": instance,
            "request_id": request_id,
        }
        if self.issues is not None:
            body["errors"] = self.issues[:MAX_ERRORS]
        return body


def problem_response(
    status_code: int,
    code: str,
    detail: str,
    *,
    instance: str,
    request_id: str,
    issues: list[dict[str, str]] | None = None,
) -> JSONResponse:
    """Собрать `JSONResponse` в формате problem+json.

    Args:
        status_code: HTTP-код.
        code: Ключ каталога типов ошибок.
        detail: Пояснение для клиента.
        instance: Путь запроса.
        request_id: Идентификатор корреляции.
        issues: Ошибки валидации (только для 422).

    Returns:
        Ответ с заголовками `Content-Type` и `X-Request-ID`.
    """
    error = ApiError(status_code, code, detail, issues=issues)
    body = error.to_problem(instance=instance, request_id=request_id)
    return JSONResponse(
        status_code=status_code,
        content=body,
        media_type=PROBLEM_MEDIA_TYPE,
        headers={"X-Request-ID": request_id},
    )


def request_id_of(request: Request) -> str:
    """Идентификатор корреляции запроса (`X-Request-ID`, `docs/api.md` §3).

    Заголовок-эхо и валидация входящего значения появятся в T3.1; здесь
    гарантируется, что ошибка всегда содержит идентификатор.

    Args:
        request: Запрос FastAPI.

    Returns:
        Идентификатор из `request.state` или свежий UUID4.
    """
    existing = getattr(request.state, "request_id", None)
    if isinstance(existing, str) and existing:
        return existing
    return str(uuid.uuid4())


async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    """Обработчик `ApiError`: превратить исключение в problem+json.

    Args:
        request: Запрос FastAPI (источник `instance` и `request_id`).
        exc: Ошибка API с кодом и деталями.

    Returns:
        Ответ RFC 7807 с согласованным HTTP-кодом.
    """
    return problem_response(
        exc.status_code,
        exc.code,
        exc.detail,
        instance=request.url.path,
        request_id=request_id_of(request),
        issues=exc.issues,
    )
