"""Pydantic-схемы ответов ClicKit Cloud.

Схемы попадают в OpenAPI, поэтому описания полей дублируют `docs/api.md`
дословно — контракт виден и в документации API, и в коде.
"""

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
