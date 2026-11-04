"""Эндпоинты сценариев ClicKit Cloud (`/v1/scenarios`).

Контракт — `docs/api.md` §5.5–5.8: публикация (201), скачивание (200/304),
список (200) и удаление (204). Валидация IR выполняется кодом
`core.ir.schema` (ADR №37), решение по `Idempotency-Key` — в
`scenario_service.publish`, доступ к БД — в `repository.SqlScenarioRepository`.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status
from sqlalchemy.orm import Session

from service.app.api.deps import (
    get_session,
    get_settings,
    parse_uuid,
    require_delete_key,
    require_write_key,
    scenario_metadata,
)
from service.app.errors import ApiError
from service.app.repository import SqlScenarioRepository
from service.app.scenario_service import (
    MAX_DESCRIPTION_LENGTH,
    PublicationValidationError,
    ScenarioConflictError,
    ValidatedPublication,
    build_publication,
    normalize_idempotency_key,
    publish,
    request_body_hash,
)
from service.app.schemas import (
    ProblemDetails,
    ScenarioCreatedResponse,
    ScenarioMetadata,
    ScenarioPageResponse,
)
from service.app.version import SERVICE_NAME

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/scenarios", tags=["scenarios"])

#: Ошибки маршрутов сценариев в формате problem+json (`docs/api.md` §4).
PROBLEM_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"model": ProblemDetails, "description": "Ключ не передан или неверен"},
    403: {"model": ProblemDetails, "description": "Ключ не даёт прав на метод"},
    404: {"model": ProblemDetails, "description": "Сценарий не найден"},
    409: {"model": ProblemDetails, "description": "Конфликт Idempotency-Key"},
    413: {"model": ProblemDetails, "description": "Тело больше лимита"},
    415: {"model": ProblemDetails, "description": "Content-Type не JSON"},
    422: {"model": ProblemDetails, "description": "Схема запроса или IR невалидны"},
    503: {"model": ProblemDetails, "description": "База данных недоступна"},
}

#: Схема тела публикации для OpenAPI: тело читается вручную (нужен контроль
#: размера до разбора), поэтому схема описывается явно (`docs/api.md` §5.5).
CREATE_REQUEST_BODY: dict[str, Any] = {
    "required": True,
    "content": {
        "application/json": {
            "schema": {
                "type": "object",
                "required": ["scenario"],
                "properties": {
                    "name": {
                        "type": "string",
                        "maxLength": 200,
                        "description": (
                            "Имя сценария; по умолчанию берётся из scenario.name"
                        ),
                    },
                    "description": {
                        "type": "string",
                        "maxLength": MAX_DESCRIPTION_LENGTH,
                        "description": "Описание сценария (по умолчанию '')",
                    },
                    "scenario": {
                        "type": "object",
                        "description": "IR-сценарий .acl.json v1",
                    },
                },
            }
        }
    },
}

#: Символы, недопустимые в имени файла `Content-Disposition`.
_UNSAFE_FILENAME_RE = re.compile(r"[^0-9A-Za-z_.\- ]+")

SessionDep = Annotated[Session, Depends(get_session)]
#: Зависимость «ключ записи» (`docs/api.md` §2).
WriteKeyDep = Annotated[None, Depends(require_write_key)]
#: Зависимость «ключ удаления» (admin-ключ или ключ записи).
DeleteKeyDep = Annotated[None, Depends(require_delete_key)]


@router.post(
    "",
    response_model=ScenarioCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Опубликовать сценарий",
    description=(
        "Принимает IR `.acl.json`, валидирует его через `core.ir.schema` и "
        "сохраняет нормализованный документ (docs/api.md §5.5)."
    ),
    responses=PROBLEM_RESPONSES,
    openapi_extra={"requestBody": CREATE_REQUEST_BODY},
)
async def create_scenario(
    request: Request,
    response: Response,
    session: SessionDep,
    _: WriteKeyDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> ScenarioCreatedResponse:
    """Создать сценарий с учётом `Idempotency-Key`."""
    settings = get_settings(request)
    payload = await read_json_body(request)
    key = parse_idempotency_key(idempotency_key)
    publication = parse_publication(payload)

    repository = SqlScenarioRepository(session)
    try:
        record, replay = publish(
            repository,
            publication,
            idempotency_key=key,
            idempotency_body=request_body_hash(payload),
            ttl_hours=settings.idempotency_ttl_hours,
        )
    except ScenarioConflictError as exc:
        raise ApiError(409, "conflict", str(exc)) from exc

    if replay:
        response.headers["Idempotent-Replay"] = "true"
    url = f"/v1/scenarios/{record.id}"
    response.headers["Location"] = url
    return ScenarioCreatedResponse(**scenario_metadata(record), url=url)


@router.get(
    "",
    response_model=ScenarioPageResponse,
    summary="Список сценариев",
    description=(
        "Отдаёт метаданные без полного IR, сортировка по `created_at` DESC "
        "(docs/api.md §5.7)."
    ),
    responses=PROBLEM_RESPONSES,
)
def list_scenarios(
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ScenarioPageResponse:
    """Отдать страницу списка сценариев."""
    items, total = SqlScenarioRepository(session).list_page(limit=limit, offset=offset)
    return ScenarioPageResponse(
        items=[ScenarioMetadata(**scenario_metadata(item)) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{scenario_id}",
    response_model=None,
    summary="Скачать сценарий",
    description=(
        "Отдаёт полный `.acl.json` с `ETag` и поддержкой `If-None-Match` "
        "(docs/api.md §5.6)."
    ),
    responses={
        **PROBLEM_RESPONSES,
        304: {"description": "Документ не изменился (If-None-Match)"},
        200: {
            "description": "Полный документ .acl.json",
            "content": {"application/json": {"schema": {"type": "object"}}},
        },
    },
)
def download_scenario(
    session: SessionDep,
    scenario_id: str,
    if_none_match: Annotated[str | None, Header(alias="If-None-Match")] = None,
) -> Response:
    """Отдать полный документ сценария (или 304 при совпадении `ETag`)."""
    record = SqlScenarioRepository(session).get(parse_uuid(scenario_id))
    if record is None:
        raise not_found(scenario_id)

    etag = f'"{record.sha256}"'
    if if_none_match is not None and _etag_matches(if_none_match, etag):
        return Response(
            status_code=status.HTTP_304_NOT_MODIFIED, headers={"ETag": etag}
        )

    body = json.dumps(record.ir, sort_keys=True, ensure_ascii=False)
    return Response(
        content=body,
        media_type="application/json",
        headers={
            "ETag": etag,
            "Content-Disposition": (
                f'attachment; filename="{_safe_filename(record.name)}.acl.json"'
            ),
        },
    )


@router.delete(
    "/{scenario_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Удалить сценарий",
    description="Требует API-ключ; повторное удаление — 404 (docs/api.md §5.8).",
    responses=PROBLEM_RESPONSES,
)
def delete_scenario(
    session: SessionDep,
    _: DeleteKeyDep,
    scenario_id: str,
) -> Response:
    """Удалить сценарий по идентификатору."""
    repository = SqlScenarioRepository(session)
    record = repository.get(parse_uuid(scenario_id))
    if record is None:
        raise not_found(scenario_id)
    repository.delete(record)
    repository.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def read_json_body(request: Request) -> Any:
    """Прочитать JSON-тело запроса с проверкой типа содержимого.

    Размер тела ограничен общим слоем `BodySizeLimitMiddleware` до разбора
    (`docs/api.md` §6), поэтому здесь остаются только тип и корректность JSON.

    Args:
        request: Запрос FastAPI.

    Returns:
        Разобранное JSON-значение.

    Raises:
        ApiError: 415 — тип содержимого не JSON; 422 — тело пустое или не
            является корректным JSON.
    """
    if "application/json" not in request.headers.get("content-type", ""):
        raise ApiError(
            415,
            "unsupported-media-type",
            "Content-Type должен быть application/json",
        )

    raw = await request.body()
    if not raw:
        raise ApiError(
            422,
            "validation",
            "Тело запроса пустое",
            issues=[{"path": "$", "message": "ожидается JSON-объект"}],
        )
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.info("Некорректный JSON от клиента: %s", exc.msg)
        raise ApiError(
            422,
            "validation",
            "Тело запроса не является корректным JSON",
            issues=[{"path": "$", "message": exc.msg}],
        ) from exc


def parse_idempotency_key(raw: str | None) -> str | None:
    """Проверить заголовок `Idempotency-Key` (`docs/api.md` §7).

    Args:
        raw: Значение заголовка или `None`.

    Returns:
        Ключ без крайних пробелов или `None`, если заголовок не задан.

    Raises:
        ApiError: 422 — ключ не подходит по длине или составу символов.
    """
    try:
        return normalize_idempotency_key(raw)
    except ValueError as exc:
        raise ApiError(
            422,
            "validation",
            str(exc),
            issues=[{"path": "Idempotency-Key", "message": str(exc)}],
        ) from exc


def parse_publication(payload: Any) -> ValidatedPublication:
    """Проверить тело публикации и вернуть `ValidatedPublication`.

    Args:
        payload: Разобранное JSON-тело запроса.

    Returns:
        Проверенная публикация (имя, описание, нормализованный IR, хэш).

    Raises:
        ApiError: 422 — тело не объект, либо имя/описание/IR невалидны.
    """
    if not isinstance(payload, dict):
        raise ApiError(
            422,
            "validation",
            "Тело запроса должно быть JSON-объектом",
            issues=[{"path": "$", "message": "ожидается JSON-объект"}],
        )
    try:
        return build_publication(
            name=payload.get("name"),
            description=payload.get("description"),
            scenario=payload.get("scenario"),
        )
    except PublicationValidationError as exc:
        raise ApiError(
            422,
            "validation",
            f"Сценарий не прошёл проверку: ошибок {len(exc.issues)}",
            issues=exc.issues,
        ) from exc


def not_found(scenario_id: str) -> ApiError:
    """Ошибка 404 для неизвестного идентификатора."""
    return ApiError(404, "not-found", f"Сценарий {scenario_id} не найден")


def _etag_matches(header: str, etag: str) -> bool:
    """Совпадает ли `If-None-Match` с текущим `ETag`.

    Для `GET` RFC 9110 предписывает слабое сравнение, поэтому префикс `W/`
    отбрасывается; `*` соответствует любому документу.
    """
    candidates = {
        _strip_weak(part.strip()) for part in header.split(",") if part.strip()
    }
    return "*" in candidates or etag in candidates


def _strip_weak(value: str) -> str:
    """Убрать префикс слабого валидатора (`W/`) из entity-tag."""
    if value[:2].upper() == "W/":
        return value[2:]
    return value


def _safe_filename(name: str) -> str:
    """Очистить имя сценария для `Content-Disposition` (`docs/api.md` §5.6).

    Управляющие символы, кавычки и разделители пути заменяются подчёркиванием,
    повторы точек сворачиваются, ведущие точки убираются — иначе имя файла
    могло бы содержать `..` и сбить клиента при сохранении.
    """
    cleaned = _UNSAFE_FILENAME_RE.sub("_", name).strip()
    cleaned = re.sub(r"\.{2,}", ".", cleaned).lstrip(".").strip()
    return cleaned or SERVICE_NAME
