"""Приложение ClicKit Cloud: сборка FastAPI, настройки и системные роутеры.

Запуск: `uvicorn service.app.main:app` (см. `docs/api.md` §9 — без
`CLICKIT_API_KEY` сервис не стартует, fail-closed). Настройки читаются в
`lifespan`, а не при импорте модуля: импорт не требует окружения, поэтому
тесты и инструменты (OpenAPI, статический анализ) работают без секретов.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware import Middleware

from service.app.api.v1 import crash_reports, health, scenarios
from service.app.config import Settings, load_settings
from service.app.db import Database, DatabaseProtocol
from service.app.errors import (
    ApiError,
    api_error_handler,
    http_exception_handler,
    unhandled_exception_handler,
    validation_error_handler,
)
from service.app.middleware import BodySizeLimitMiddleware
from service.app.observability.logging import configure_logging
from service.app.observability.metrics import HttpMetricsMiddleware, ServiceMetrics
from service.app.observability.tracing import (
    TRACING_ENABLED_KEY,
    Tracing,
    TracingSetup,
)
from service.app.request_id import RequestContextMiddleware
from service.app.version import SERVICE_NAME, SERVICE_VERSION

logger = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None,
    database: DatabaseProtocol | None = None,
    tracing: TracingSetup | None = None,
    *,
    enable_tracing: bool | None = None,
) -> FastAPI:
    """Собрать приложение ClicKit Cloud.

    Args:
        settings: Готовые настройки (тесты); `None` — прочитать окружение
            при старте приложения.
        database: Готовое подключение к БД (тесты); `None` — создать по
            `CLICKIT_DB_URL` в `lifespan`.
        tracing: Настройка трейсинга (тесты — с экспортёром в память);
            `None` — `Tracing` с OTLP-экспортом по настройкам.
        enable_tracing: Явный переключатель трейсинга; `None` — при явных
            настройках трейсинг выключен («без сети»), иначе берётся из
            окружения. Второй признак нужен, потому что `Settings`
            по умолчанию содержит `otel_enabled=True` (контракт env), а
            `create_app(Settings(...))` — это конфигурация процесса-теста:
            запускать OTLP-экспорт там, где нет коллектора, нельзя и
            невозможно заметить по настройкам.

    Returns:
        Приложение с системными роутерами и настроенным жизненным циклом.
    """
    # Реестр метрик создаётся при сборке приложения: у каждого экземпляра
    # (включая тестовые) свой, поэтому счётчики не «протекают» между
    # приложениями и не конфликтуют в глобальном реестре prometheus_client.
    metrics = ServiceMetrics()
    tracing_setup: TracingSetup = tracing if tracing is not None else Tracing()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        resolved = settings if settings is not None else load_settings()
        resolved.validate()
        configure_logging(
            resolved.log_level,
            secrets=(resolved.api_key, resolved.admin_api_key),
        )
        app.state.settings = resolved
        app.state.metrics = metrics
        app.state.database = (
            database if database is not None else Database(resolved.require_db_url())
        )
        # Трейсинг включается, только если этого хочет и приложение, и его
        # настройки. Явные настройки по умолчанию означают «без сети»
        # (тесты и диагностика): иначе каждый тест при остановке ждал бы
        # экспорт в несуществующий коллектор по таймауту (5 с), и прогон
        # сервиса «висел».
        if enable_tracing is None:
            wanted = resolved.otel_enabled if settings is None else False
        else:
            wanted = enable_tracing and resolved.otel_enabled
        tracing_wanted = wanted and getattr(tracing_setup, "enabled", True)
        if tracing_wanted:
            # Включение идёт в пуле потоков: провайдер SDK глобальный на
            # процесс, поэтому проверка и назначение должны быть атомарны, а
            # подготовка экспортёра не должна блокировать цикл событий на
            # старте. Второй `start` у другого приложения в том же процессе
            # — безопасное отсутствие действия (см. `Tracing.start`).
            try:
                await run_in_threadpool(tracing_setup.start, app, settings=resolved)
            except Exception:  # noqa: BLE001 — трейсинг не должен ронять сервис
                logger.exception("Не удалось включить трейсинг, работаем без него")
            else:
                setattr(app.state, TRACING_ENABLED_KEY, True)
        logger.info(
            "%s %s запущен (git %s)", SERVICE_NAME, SERVICE_VERSION, resolved.git_sha
        )
        try:
            yield
        finally:
            # Остановка экспортёра отправляет накопленный батч: она тоже не
            # должна держать цикл событий (например, при долгом коллекторе).
            try:
                await run_in_threadpool(tracing_setup.shutdown)
            except Exception:  # noqa: BLE001 — завершение не должно падать
                logger.exception("Ошибка при остановке трейсинга")
            setattr(app.state, TRACING_ENABLED_KEY, False)
            app.state.database.dispose()
            logger.info("%s остановлен", SERVICE_NAME)

    app = FastAPI(
        title="ClicKit Cloud",
        version=SERVICE_VERSION,
        description="HTTP-сервис публикации сценариев ClicKit и crash-отчётов.",
        lifespan=lifespan,
        # Порядок важен: RequestContextMiddleware стоит первым и потому
        # оказывается внешним — идентификатор есть даже у ответа 413 лимита
        # тела. Метрики — сразу под ним: у запроса уже есть `request_id`, а
        # 413 лимита тела попадает и в метрики, и в журнал. Слой журнального
        # `trace_id` (T1.3) вставляет `Tracing.start` уже в построенный
        # стек: инструментация FastAPI оборачивает всё приложение снаружи,
        # и слой оказывается внутри HTTP-спана.
        # В списке `middleware=[...]` первым идёт **самый внешний** слой —
        # зеркально `add_middleware`, где внешним становится последний
        # добавленный.
        middleware=[
            Middleware(RequestContextMiddleware),
            Middleware(HttpMetricsMiddleware),
            Middleware(BodySizeLimitMiddleware),
        ],
    )
    app.state.metrics = metrics
    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
    app.include_router(health.router)
    app.include_router(scenarios.router)
    app.include_router(crash_reports.router)
    return app


#: Точка входа для uvicorn: `uvicorn service.app.main:app`.
app = create_app()
