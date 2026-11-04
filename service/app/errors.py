"""Ошибки API ClicKit Cloud в формате RFC 7807 (`application/problem+json`).

Единая точка формирования ответов об ошибках: контракт `docs/api.md` §4
описывает поля `type`, `title`, `status`, `detail`, `instance`, `request_id`
и необязательный список `errors` (пути валидации, до 50 записей). Модуль
намеренно не импортирует FastAPI-специфику ответа — это обычный `JSONResponse`,
поэтому обработчики можно регистрировать и без запуска приложения.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)

#: Базовый префикс стабильных URN-типов ошибок (`docs/api.md` §4).
TYPE_PREFIX = "urn:clikit:error:"
#: Content-Type ошибок по RFC 7807.
PROBLEM_MEDIA_TYPE = "application/problem+json"
#: Максимум записей в списке `errors` (совпадает с лимитом IR).
MAX_ERRORS = 50

#: Код ошибки → (URN-тип, короткий заголовок). Заголовки совпадают с §4.
CATALOG: dict[str, tuple[str, str]] = {
    "bad-request": (f"{TYPE_PREFIX}bad-request", "Некорректный запрос"),
    "unauthorized": (f"{TYPE_PREFIX}unauthorized", "Требуется API-ключ"),
    "forbidden": (f"{TYPE_PREFIX}forbidden", "Недостаточно прав"),
    "not-found": (f"{TYPE_PREFIX}not-found", "Ресурс не найден"),
    "method-not-allowed": (
        f"{TYPE_PREFIX}method-not-allowed",
        "Метод не поддерживается",
    ),
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

#: HTTP-код → код каталога для ошибок, поднятых Starlette/FastAPI.
STATUS_TO_CODE: dict[int, str] = {
    400: "bad-request",
    401: "unauthorized",
    403: "forbidden",
    404: "not-found",
    405: "method-not-allowed",
    409: "conflict",
    413: "payload-too-large",
    415: "unsupported-media-type",
    422: "validation",
    503: "unavailable",
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
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    """Собрать `JSONResponse` в формате problem+json.

    Args:
        status_code: HTTP-код.
        code: Ключ каталога типов ошибок.
        detail: Пояснение для клиента.
        instance: Путь запроса.
        request_id: Идентификатор корреляции.
        issues: Ошибки валидации (только для 422).
        headers: Дополнительные заголовки (например, `Allow` у 405).

    Returns:
        Ответ с заголовками `Content-Type` и `X-Request-ID`.
    """
    error = ApiError(status_code, code, detail, issues=issues)
    body = error.to_problem(instance=instance, request_id=request_id)
    response_headers = {"X-Request-ID": request_id}
    if headers:
        response_headers.update(headers)
    return JSONResponse(
        status_code=status_code,
        content=body,
        media_type=PROBLEM_MEDIA_TYPE,
        headers=response_headers,
    )


def request_id_of(request: Request) -> str:
    """Идентификатор корреляции запроса (`X-Request-ID`, `docs/api.md` §3).

    Значение кладёт `RequestContextMiddleware`; если обработчик вызван вне
    него, создаётся свежий UUID4, чтобы ответ ошибки не остался без
    корреляции.

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


def _format_location(loc: Sequence[Any]) -> str:
    """Превратить `loc` ошибки FastAPI в путь контракта (`docs/api.md` §4).

    FastAPI даёт кортежи вида `("query", "limit")`; служебный префикс
    (`body`, `query`, `path`, `header`, `cookie`) отбрасывается, а индексы
    списков записываются как `[0]` — так путь совпадает с путями IR.

    Args:
        loc: Кортеж местоположения из `ValidationError`.

    Returns:
        Путь вида `limit` или `nodes[0].x`; для пустого — `$`.
    """
    parts: list[str] = []
    for index, item in enumerate(loc):
        if index == 0 and item in {"body", "query", "path", "header", "cookie"}:
            continue
        if isinstance(item, int):
            parts.append(f"[{item}]")
        else:
            parts.append(f".{item}" if parts else str(item))
    return "".join(parts) or "$"


async def validation_error_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """Обработчик `RequestValidationError`: 422 в формате problem+json.

    Без него FastAPI отдаёт собственный JSON `{"detail": [...]}`, из-за чего
    клиент получал бы два разных формата ошибок.

    Args:
        request: Запрос FastAPI.
        exc: Ошибка валидации параметров запроса.

    Returns:
        Ответ 422 со списком `errors` (пути в формате контракта).
    """
    issues = [
        {
            "path": _format_location(error.get("loc", ())),
            "message": str(error.get("msg", "некорректное значение")),
        }
        for error in exc.errors()[:MAX_ERRORS]
    ]
    return problem_response(
        422,
        "validation",
        f"Запрос не прошёл проверку: ошибок {len(issues)}",
        instance=request.url.path,
        request_id=request_id_of(request),
        issues=issues,
    )


async def http_exception_handler(
    request: Request,
    exc: StarletteHTTPException,
) -> JSONResponse:
    """Обработчик `HTTPException` Starlette/FastAPI в формате problem+json.

    Args:
        request: Запрос FastAPI.
        exc: HTTP-исключение (404 неизвестного пути, 405, 401 и т. п.).

    Returns:
        Ответ RFC 7807 с исходным кодом и заголовками исключения.
    """
    code = STATUS_TO_CODE.get(
        exc.status_code, "internal" if exc.status_code >= 500 else "bad-request"
    )
    detail = exc.detail if isinstance(exc.detail, str) else "Ошибка запроса"
    return problem_response(
        exc.status_code,
        code,
        detail,
        instance=request.url.path,
        request_id=request_id_of(request),
        headers=exc.headers,
    )


async def unhandled_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """Обработчик неожиданных исключений: 500 без деталей наружу.

    Подробности (включая traceback) остаются в журнале с `request_id`;
    клиент получает стабильный problem+json, а не HTML/пустой ответ.

    Args:
        request: Запрос FastAPI.
        exc: Необработанное исключение.

    Returns:
        Ответ 500 `urn:clikit:error:internal`.
    """
    request_id = request_id_of(request)
    logger.exception(
        "Необработанная ошибка сервиса (request_id=%s)", request_id, exc_info=exc
    )
    return problem_response(
        500,
        "internal",
        "Внутренняя ошибка сервиса",
        instance=request.url.path,
        request_id=request_id,
    )
