"""Клиент ClicKit Cloud: обмен сценариями с HTTP-сервисом (M7 T4.2).

Пакет не импортирует `core/` и `gui/` и не используется desktop-приложением
напрямую: точка входа — консольный скрипт `scripts/cloud_publish.py`
(контракт — `docs/api.md` §10).
"""

from __future__ import annotations

from cloud.client import (
    CloudAuthError,
    CloudClient,
    CloudConflictError,
    CloudError,
    CloudNotFoundError,
    CloudServerError,
    CloudTooLargeError,
    CloudValidationError,
    CrashReceipt,
    PublishedScenario,
    ScenarioPage,
)

__all__ = [
    "CloudAuthError",
    "CloudClient",
    "CloudConflictError",
    "CloudError",
    "CloudNotFoundError",
    "CloudServerError",
    "CloudTooLargeError",
    "CloudValidationError",
    "CrashReceipt",
    "PublishedScenario",
    "ScenarioPage",
]
