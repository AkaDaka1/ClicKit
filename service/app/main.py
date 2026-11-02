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

from service.app.api.v1 import health
from service.app.config import Settings, load_settings
from service.app.version import SERVICE_NAME, SERVICE_VERSION

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Собрать приложение ClicKit Cloud.

    Args:
        settings: Готовые настройки (тесты); `None` — прочитать окружение
            при старте приложения.

    Returns:
        Приложение с системными роутерами и настроенным жизненным циклом.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        resolved = settings if settings is not None else load_settings()
        resolved.validate()
        logging.basicConfig(
            level=resolved.log_level,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )
        app.state.settings = resolved
        logger.info(
            "%s %s запущен (git %s)", SERVICE_NAME, SERVICE_VERSION, resolved.git_sha
        )
        yield
        logger.info("%s остановлен", SERVICE_NAME)

    app = FastAPI(
        title="ClicKit Cloud",
        version=SERVICE_VERSION,
        description="HTTP-сервис публикации сценариев ClicKit и crash-отчётов.",
        lifespan=lifespan,
    )
    app.include_router(health.router)
    return app


#: Точка входа для uvicorn: `uvicorn service.app.main:app`.
app = create_app()
