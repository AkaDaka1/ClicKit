"""Системные эндпоинты ClicKit Cloud: liveness, readiness, версия и метрики.

`/healthz` не трогает БД (иначе упавшая база «убивала» бы живой процесс),
`/readyz` проверяет `SELECT 1` и отвечает 503 при недоступной БД — см.
`docs/api.md` §5.1–5.2.
"""

from __future__ import annotations

from fastapi import APIRouter, Request, Response, status
from fastapi.responses import PlainTextResponse

from core.ir.nodes import SCENARIO_VERSION
from service.app.config import Settings
from service.app.observability.metrics import (
    METRICS_CONTENT_TYPE,
    ServiceMetrics,
    render_metrics,
)
from service.app.schemas import (
    HealthResponse,
    ReadinessChecks,
    ReadinessResponse,
    VersionResponse,
)
from service.app.version import SERVICE_NAME, SERVICE_VERSION

router = APIRouter(tags=["system"])


@router.get(
    "/healthz",
    response_model=HealthResponse,
    summary="Liveness-проверка",
    description="Отвечает 200 без обращения к БД (docs/api.md §5.1).",
)
def healthz() -> HealthResponse:
    """Сообщить, что процесс жив (БД не проверяется)."""
    return HealthResponse(status="ok", service=SERVICE_NAME, version=SERVICE_VERSION)


@router.get(
    "/readyz",
    response_model=ReadinessResponse,
    summary="Readiness-проверка с БД",
    description="Выполняет `SELECT 1`; 503 при недоступной БД (docs/api.md §5.2).",
    responses={
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": ReadinessResponse,
            "description": "БД недоступна",
        }
    },
)
def readyz(request: Request, response: Response) -> ReadinessResponse:
    """Проверить готовность принимать запросы (доступность БД)."""
    database = getattr(request.app.state, "database", None)
    ready = database is not None and database.check()
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(
        status="ready" if ready else "unavailable",
        checks=ReadinessChecks(database="ok" if ready else "error"),
    )


@router.get(
    "/version",
    response_model=VersionResponse,
    summary="Версия и сведения о сборке",
    description="Версия сервиса, git-коммит сборки и версия формата IR.",
)
def version(request: Request) -> VersionResponse:
    """Отдать версию сервиса и параметры сборки из настроек."""
    settings: Settings = request.app.state.settings
    return VersionResponse(
        service=SERVICE_NAME,
        version=SERVICE_VERSION,
        git_sha=settings.git_sha,
        built_at=settings.build_time,
        ir_format_version=SCENARIO_VERSION,
    )


@router.get(
    "/metrics",
    response_class=PlainTextResponse,
    summary="Метрики Prometheus",
    description=(
        "HTTP-метрики, состояние пула БД и сведения о сборке "
        "(контракт — `docs/sre/slo.md` §8)."
    ),
    response_description="Текст в формате Prometheus (`text/plain; version=1.0.0`)",
)
async def metrics(request: Request) -> PlainTextResponse:
    """Отдать метрики в текстовом формате Prometheus (M8 T1.2).

    Обработчик **асинхронный** намеренно: на синхронных обработчиках FastAPI
    выполняет их в пуле потоков, а слой метрик снимает «в обработке» лишь
    после возврата управления — `/metrics` показывал бы сам себя в gauge.
    """
    state = request.app.state
    settings: Settings = state.settings
    collector: ServiceMetrics = state.metrics
    database = getattr(state, "database", None)
    pool_samples = getattr(database, "pool_samples", None)
    body = render_metrics(
        collector,
        pool_samples=pool_samples if callable(pool_samples) else None,
        build_labels=lambda: {"version": SERVICE_VERSION, "git_sha": settings.git_sha},
    )
    return PlainTextResponse(body, media_type=METRICS_CONTENT_TYPE)
