"""Проверка API-ключей ClicKit Cloud (`docs/api.md` §2).

Правила ролей — чистые функции без FastAPI: их легко проверить отдельно от
маршрутов. Ключ сравнивается за постоянное время (`hmac.compare_digest`),
в логи и ответы он не попадает (ADR №38, §54 в `AI_CONTEXT.md`).

Роли разделены намеренно:

* ``write`` — публикация сценариев (`CLICKIT_API_KEY`);
* ``admin`` — удаление (`CLICKIT_ADMIN_API_KEY`), если он задан.

Ключ, который не совпал ни с одним из настроенных, — 401; совпал, но не даёт
права на метод (например, write-ключ на `DELETE` при заданном admin-ключе) —
403.
"""

from __future__ import annotations

import hmac
from collections.abc import Collection

from service.app.config import Settings
from service.app.errors import ApiError

#: Роль ключа записи (публикация сценариев).
WRITE_ROLE = "write"
#: Роль административного ключа (удаление).
ADMIN_ROLE = "admin"

#: Роли, которым разрешена публикация.
WRITE_ALLOWED = frozenset({WRITE_ROLE})


def parse_api_key(raw: str | None) -> str | None:
    """Нормализовать значение заголовка `X-API-Key`.

    Args:
        raw: Значение заголовка или `None`.

    Returns:
        Ключ без крайних пробелов или `None`, если заголовок пуст.
    """
    if raw is None:
        return None
    cleaned = raw.strip()
    return cleaned or None


def keys_match(provided: str | None, expected: str | None) -> bool:
    """Сравнить ключи за постоянное время.

    Args:
        provided: Ключ из запроса.
        expected: Настроенный ключ или `None`, если роль не сконфигурирована.

    Returns:
        `True`, только если оба ключа непусты и совпадают.
    """
    if not provided or not expected:
        return False
    return hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8"))


def resolve_role(settings: Settings, provided: str | None) -> str | None:
    """Определить роль переданного ключа.

    Оба ключа сравниваются всегда (даже если первый совпал), чтобы время
    проверки не зависело от того, какая роль сработала.

    Args:
        settings: Настройки сервиса с ключами из env.
        provided: Значение заголовка `X-API-Key`.

    Returns:
        `WRITE_ROLE`, `ADMIN_ROLE` или `None`, если ключ не подошёл.
    """
    key = parse_api_key(provided)
    if key is None:
        return None
    is_admin = keys_match(key, settings.admin_api_key)
    is_write = keys_match(key, settings.api_key)
    if is_admin:
        return ADMIN_ROLE
    if is_write:
        return WRITE_ROLE
    return None


def authorize(
    settings: Settings,
    provided: str | None,
    *,
    allowed: Collection[str],
) -> str:
    """Проверить, что ключ передан и его роль разрешает метод.

    Args:
        settings: Настройки сервиса с ключами из env.
        provided: Значение заголовка `X-API-Key`.
        allowed: Роли, которым разрешён метод.

    Returns:
        Роль, с которой выполнен запрос.

    Raises:
        ApiError: 401 — ключ отсутствует или неверен; 403 — ключ верен, но
            роль не входит в `allowed`.
    """
    role = resolve_role(settings, provided)
    if role is None:
        raise ApiError(
            401,
            "unauthorized",
            "Заголовок X-API-Key отсутствует или неверен",
        )
    if role not in allowed:
        raise ApiError(
            403,
            "forbidden",
            "Ключ не имеет прав на этот метод",
        )
    return role


def delete_allowed_roles(settings: Settings) -> frozenset[str]:
    """Роли, которым разрешено удаление сценария (`docs/api.md` §2).

    Если `CLICKIT_ADMIN_API_KEY` задан, удалять может только он: write-ключ
    на `DELETE` получает 403. Иначе используется обычный ключ записи.

    Args:
        settings: Настройки сервиса.

    Returns:
        Множество допустимых ролей для `DELETE /v1/scenarios/{id}`.
    """
    if settings.admin_api_key:
        return frozenset({ADMIN_ROLE})
    return frozenset({WRITE_ROLE})
