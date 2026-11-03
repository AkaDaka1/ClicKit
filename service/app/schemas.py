"""Pydantic-схемы ответов ClicKit Cloud.

Схемы попадают в OpenAPI, поэтому описания полей дублируют `docs/api.md`
дословно — контракт виден и в документации API, и в коде.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Ответ liveness-проверки (`GET /healthz`)."""

    status: str = Field(description="Всегда 'ok'")
    service: str = Field(description="Имя сервиса")
    version: str = Field(description="Версия сервиса")


class VersionResponse(BaseModel):
    """Ответ версии и сведений о сборке (`GET /version`)."""

    service: str = Field(description="Имя сервиса")
    version: str = Field(description="Версия сервиса")
    git_sha: str = Field(description="Коммит сборки или 'unknown'")
    built_at: str = Field(description="Время сборки (RFC 3339) или пустая строка")
    ir_format_version: int = Field(description="Версия формата IR (core.ir.nodes)")


class ReadinessChecks(BaseModel):
    """Результаты проверок готовности (`GET /readyz`)."""

    database: str = Field(description="'ok' или 'error'")


class ReadinessResponse(BaseModel):
    """Ответ readiness-проверки: 200 при готовности, 503 при сбое БД."""

    status: str = Field(description="'ready' или 'unavailable'")
    checks: ReadinessChecks = Field(description="Результаты зависимостей")


class ScenarioMetadata(BaseModel):
    """Метаданные опубликованного сценария (без полного IR)."""

    id: str = Field(description="UUIDv4 сценария")
    name: str = Field(description="Имя сценария")
    description: str = Field(description="Описание сценария")
    sha256: str = Field(description="Канонический хэш IR (ETag)")
    created_at: str = Field(description="Время создания (RFC 3339, UTC)")
    updated_at: str = Field(description="Время обновления (RFC 3339, UTC)")


class ScenarioCreatedResponse(ScenarioMetadata):
    """Ответ 201 на публикацию (`docs/api.md` §5.5)."""

    url: str = Field(description="Путь скачивания сценария")


class ScenarioPageResponse(BaseModel):
    """Ответ страницы списка сценариев (`docs/api.md` §5.7)."""

    items: list[ScenarioMetadata] = Field(description="Сценарии страницы")
    total: int = Field(description="Полное число сценариев")
    limit: int = Field(description="Размер страницы")
    offset: int = Field(description="Смещение")


class ProblemDetailError(BaseModel):
    """Одна ошибка валидации в problem+json (`docs/api.md` §4)."""

    path: str = Field(description="Путь до поля, например nodes[0].x")
    message: str = Field(description="Понятное описание ошибки")


class ProblemDetails(BaseModel):
    """Тело ошибки RFC 7807 (`docs/api.md` §4)."""

    type: str = Field(description="Стабильный URN типа ошибки")
    title: str = Field(description="Короткий заголовок")
    status: int = Field(description="HTTP-код")
    detail: str = Field(description="Человекочитаемая деталь")
    instance: str = Field(description="Путь запроса")
    request_id: str = Field(description="Идентификатор корреляции")
    errors: list[ProblemDetailError] | None = Field(
        default=None, description="Ошибки валидации (только для 422)"
    )
