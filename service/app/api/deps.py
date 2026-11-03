"""Общие хелперы маршрутов ClicKit Cloud.

Функции здесь не зависят от конкретного эндпоинта: доступ к настройкам из
`app.state`, зависимость «открыть сессию БД» и форматирование времени по
контракту (`docs/api.md` §1 — RFC 3339 в UTC с суффиксом `Z`).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from service.app.config import Settings
from service.app.db import Database
from service.app.errors import ApiError
from service.app.models import Scenario


def get_settings(request: Request) -> Settings:
    """Настройки сервиса, прочитанные в `lifespan`.

    Args:
        request: Запрос FastAPI.

    Returns:
        Настройки с заданными ключом и URL БД.
    """
    return request.app.state.settings


def require_database(request: Request) -> Database:
    """Подключение к БД или 503, если подключение не создано.

    Args:
        request: Запрос FastAPI.

    Returns:
        Подключение с фабрикой сессий.

    Raises:
        ApiError: 503 — сервис запущен без БД (например, подделкой в тестах).
    """
    database = getattr(request.app.state, "database", None)
    if database is None or not hasattr(database, "session"):
        raise ApiError(
            503,
            "unavailable",
            "База данных сервиса недоступна",
        )
    return database  # type: ignore[no-any-return]


def get_session(request: Request) -> Iterator[Session]:
    """Зависимость FastAPI: сессия БД на время запроса.

    Args:
        request: Запрос FastAPI.

    Yields:
        Открытая сессия; закрывается в конце запроса независимо от исхода.
    """
    database = require_database(request)
    session = database.session()
    try:
        yield session
    finally:
        session.close()


def parse_uuid(raw: str) -> uuid.UUID:
    """Разобрать идентификатор из пути.

    Args:
        raw: Строка из URL.

    Returns:
        `uuid.UUID`.

    Raises:
        ApiError: 422 — строка не является UUID.
    """
    try:
        return uuid.UUID(raw)
    except ValueError as exc:
        raise ApiError(
            422,
            "validation",
            "Идентификатор сценария должен быть UUID",
            issues=[{"path": "scenario_id", "message": "неверный формат UUID"}],
        ) from exc


def to_rfc3339(moment: datetime) -> str:
    """Отформатировать время как RFC 3339 в UTC (`docs/api.md` §1).

    Args:
        moment: Время из БД (`timestamptz`) или наивное UTC.

    Returns:
        Строка вида `2026-11-02T10:00:00Z`.
    """
    aware = moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)
    return aware.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def scenario_metadata(record: Scenario) -> dict[str, Any]:
    """Метаданные сценария без полного IR (`docs/api.md` §5.7).

    Args:
        record: ORM-объект сценария.

    Returns:
        Словарь полей ответа: `id`, `name`, `description`, `sha256`,
        `created_at`, `updated_at`.
    """
    return {
        "id": str(record.id),
        "name": record.name,
        "description": record.description,
        "sha256": record.sha256,
        "created_at": to_rfc3339(record.created_at),
        "updated_at": to_rfc3339(record.updated_at),
    }
