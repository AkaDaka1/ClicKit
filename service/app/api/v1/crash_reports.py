"""Эндпоинт crash-отчётов ClicKit Cloud (`/v1/crash-reports`).

Контракт — `docs/api.md` §5.9: приём отчёта о падении (202), валидация полей,
санитизация PII (домашние каталоги → `<пользователь>`), обрезка traceback
до 16 КБ. Публичный эндпоинт (без `X-API-Key`).
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from service.app.api.deps import get_session, to_rfc3339
from service.app.crash_service import (
    CrashReportValidationError,
    build_crash_report,
)
from service.app.errors import ApiError
from service.app.models import CrashReport
from service.app.schemas import CrashReceipt, ProblemDetails

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["crash-reports"])

#: Ошибки маршрута crash-отчётов в формате problem+json (`docs/api.md` §4).
PROBLEM_RESPONSES: dict[int | str, dict[str, Any]] = {
    413: {"model": ProblemDetails, "description": "Тело больше лимита"},
    415: {"model": ProblemDetails, "description": "Content-Type не JSON"},
    422: {"model": ProblemDetails, "description": "Схема запроса невалидна"},
    503: {"model": ProblemDetails, "description": "База данных недоступна"},
}

SessionDep = Annotated[Session, Depends(get_session)]


@router.post(
    "/crash-reports",
    response_model=CrashReceipt,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Приём crash-отчёта",
    description=(
        "Принимает отчёт о падении desktop-приложения, санитайзит traceback "
        "(docs/api.md §5.9). Публичный эндпоинт (без API-ключа)."
    ),
    responses=PROBLEM_RESPONSES,
)
async def create_crash_report(
    request: Request,
    session: SessionDep,
) -> CrashReceipt:
    """Принять crash-отчёт и сохранить в БД.

    Args:
        request: Запрос FastAPI с телом JSON.
        session: Сессия БД из зависимости.

    Returns:
        Идентификатор сохранённого отчёта и время приёма.

    Raises:
        ApiError: 415 (не JSON), 422 (ошибки валидации).
    """
    # Читаем и парсим JSON вручную (контроль размера через middleware).
    content_type = request.headers.get("content-type", "")
    if "application/json" not in content_type:
        raise ApiError(
            415,
            "unsupported-media-type",
            "Content-Type должен быть application/json",
        )

    try:
        payload = await request.json()
    except Exception as exc:
        raise ApiError(
            422,
            "validation",
            "Тело запроса не является корректным JSON",
            issues=[{"path": "$", "message": str(exc)}],
        ) from exc

    if not isinstance(payload, dict):
        raise ApiError(
            422,
            "validation",
            "Тело запроса должно быть JSON-объектом",
            issues=[{"path": "$", "message": "ожидается JSON-объект"}],
        )

    # Валидация и санитизация через доменный слой.
    try:
        validated = build_crash_report(
            app_version=payload.get("app_version"),
            os=payload.get("os"),
            error_hash=payload.get("error_hash"),
            traceback=payload.get("traceback"),
        )
    except CrashReportValidationError as exc:
        raise ApiError(
            422,
            "validation",
            f"Отчёт не прошёл проверку: ошибок {len(exc.issues)}",
            issues=exc.issues,
        ) from exc

    # Сохранение в БД.
    record = CrashReport(
        app_version=validated.app_version,
        os=validated.os,
        error_hash=validated.error_hash,
        traceback=validated.traceback,
    )
    try:
        session.add(record)
        session.flush()
        session.commit()
    except Exception as exc:
        logger.exception("Failed to save crash report")
        raise ApiError(
            500,
            "internal",
            "Не удалось сохранить crash-отчёт",
        ) from exc

    # Тело отчёта **не логируется** (ADR №38): только факт приёма.
    logger.info("Принят crash-отчёт %s", record.id)

    return CrashReceipt(
        id=str(record.id),
        received_at=to_rfc3339(record.created_at),
    )
