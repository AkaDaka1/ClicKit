"""Настройки сервиса ClicKit Cloud: только переменные окружения, без секретов в коде.

Контракт настроек — `docs/api.md` §9. Значения проверяются при старте
(fail-closed): лучше не запуститься с понятной ошибкой, чем принимать
запись без ключа. Модуль не импортирует FastAPI, чтобы настройки можно было
проверять в обычных тестах.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

#: Лимит тела запроса по умолчанию — 1 МБ (`docs/api.md` §6).
DEFAULT_MAX_BODY_BYTES = 1_048_576
#: Срок жизни резервации `Idempotency-Key`, часы (`docs/api.md` §7).
DEFAULT_IDEMPOTENCY_TTL_HOURS = 24
#: Минимальная длина API-ключа: короткий ключ не защищает запись.
MIN_API_KEY_LENGTH = 16
#: Допустимые уровни журналирования.
LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})
#: OTLP HTTP-адрес по умолчанию: стандартный порт OTLP/HTTP
#: (`plans/M8-observability.md` §3); путь `/v1/traces` добавляет экспортёр.
DEFAULT_OTLP_ENDPOINT = "http://localhost:4318"
#: Таймаут экспорта спанов, секунды: экспорт не должен держать запрос.
DEFAULT_SPAN_EXPORT_TIMEOUT_SECONDS = 5


class ServiceConfigError(RuntimeError):
    """Конфигурация сервиса некорректна: старт запрещён (fail-closed)."""


@dataclass(frozen=True)
class Settings:
    """Разрешённые настройки сервиса (значения уже приведены к нужным типам)."""

    api_key: str | None = None
    admin_api_key: str | None = None
    db_url: str | None = None
    max_body_bytes: int = DEFAULT_MAX_BODY_BYTES
    idempotency_ttl_hours: int = DEFAULT_IDEMPOTENCY_TTL_HOURS
    git_sha: str = "unknown"
    build_time: str = ""
    log_level: str = "INFO"
    #: Т्रेйсы OTel (M8 T1.3). `False` — трейсы выключены полностью: в логе
    #: `trace_id` остаётся `-`, экспорт в Tempo не идёт.
    otel_enabled: bool = True
    #: Адрес OTLP HTTP-приёмника (Tempo): `http://tempo:4318` в compose.
    otel_endpoint: str = DEFAULT_OTLP_ENDPOINT
    #: Доля сэмплируемых трейсов (1.0 — все, как принято локально).
    otel_sample_rate: float = 1.0
    #: Имя ресурса `service.name`; `None` — `SERVICE_NAME` сервиса.
    otel_service_name: str | None = None

    def validate(self) -> None:
        """Проверить обязательные настройки и безопасные значения.

        Raises:
            ServiceConfigError: ключ записи не задан или короче
                `MIN_API_KEY_LENGTH`, не задан URL БД, либо числовые/строковые
                значения выходят за допустимые границы.
        """
        if not self.api_key:
            raise ServiceConfigError(
                "CLICKIT_API_KEY не задан: сервис не стартует (fail-closed)"
            )
        if len(self.api_key) < MIN_API_KEY_LENGTH:
            raise ServiceConfigError(
                f"CLICKIT_API_KEY короче {MIN_API_KEY_LENGTH} символов"
            )
        if (
            self.admin_api_key is not None
            and len(self.admin_api_key) < MIN_API_KEY_LENGTH
        ):
            raise ServiceConfigError(
                f"CLICKIT_ADMIN_API_KEY короче {MIN_API_KEY_LENGTH} символов"
            )
        self.require_db_url()
        if self.max_body_bytes <= 0:
            raise ServiceConfigError("CLICKIT_MAX_BODY_BYTES должен быть больше нуля")
        if self.idempotency_ttl_hours <= 0:
            raise ServiceConfigError(
                "CLICKIT_IDEMPOTENCY_TTL_HOURS должен быть больше нуля"
            )
        if self.log_level not in LOG_LEVELS:
            allowed = ", ".join(sorted(LOG_LEVELS))
            raise ServiceConfigError(
                f"CLICKIT_LOG_LEVEL должен быть одним из: {allowed}"
            )
        if not 0.0 < self.otel_sample_rate <= 1.0:
            raise ServiceConfigError(
                "CLICKIT_OTEL_SAMPLE_RATE должен быть больше 0 и не больше 1"
            )
        if self.otel_enabled and not self.otel_endpoint:
            raise ServiceConfigError(
                "CLICKIT_OTEL_ENDPOINT не задан, хотя CLICKIT_OTEL_ENABLED=1"
            )

    def require_db_url(self) -> str:
        """Вернуть URL БД, который гарантированно задан.

        Returns:
            SQLAlchemy URL PostgreSQL из `CLICKIT_DB_URL`.

        Raises:
            ServiceConfigError: переменная не задана — сервису некуда писать
                сценарии, поэтому старт запрещён (fail-closed).
        """
        if not self.db_url:
            raise ServiceConfigError(
                "CLICKIT_DB_URL не задан: сервис не стартует (fail-closed)"
            )
        return self.db_url


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    """Прочитать настройки из окружения и проверить их.

    Args:
        env: Источник переменных окружения; по умолчанию `os.environ`
            (в тестах передаётся словарь — глобальное состояние не трогаем).

    Returns:
        Проверенные настройки сервиса.

    Raises:
        ServiceConfigError: обязательная переменная отсутствует или значение
            не приводится к нужному типу.
    """
    source = os.environ if env is None else env
    settings = Settings(
        api_key=_clean(source.get("CLICKIT_API_KEY")),
        admin_api_key=_clean(source.get("CLICKIT_ADMIN_API_KEY")),
        db_url=_clean(source.get("CLICKIT_DB_URL")),
        max_body_bytes=_env_int(
            source, "CLICKIT_MAX_BODY_BYTES", DEFAULT_MAX_BODY_BYTES
        ),
        idempotency_ttl_hours=_env_int(
            source, "CLICKIT_IDEMPOTENCY_TTL_HOURS", DEFAULT_IDEMPOTENCY_TTL_HOURS
        ),
        git_sha=_clean(source.get("CLICKIT_GIT_SHA")) or "unknown",
        build_time=_clean(source.get("CLICKIT_BUILD_TIME")) or "",
        log_level=(_clean(source.get("CLICKIT_LOG_LEVEL")) or "INFO").upper(),
        otel_enabled=_env_bool(source, "CLICKIT_OTEL_ENABLED", True),
        otel_endpoint=(
            _clean(source.get("CLICKIT_OTEL_ENDPOINT")) or DEFAULT_OTLP_ENDPOINT
        ),
        otel_sample_rate=_env_float(source, "CLICKIT_OTEL_SAMPLE_RATE", 1.0),
        otel_service_name=_clean(source.get("CLICKIT_OTEL_SERVICE_NAME")),
    )
    settings.validate()
    return settings


def _clean(value: str | None) -> str | None:
    """Убрать пробелы; пустая строка означает «не задано»."""
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _env_int(source: Mapping[str, str], name: str, default: int) -> int:
    """Прочитать целочисленную переменную окружения с понятной ошибкой."""
    value = _clean(source.get(name))
    if value is None:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ServiceConfigError(f"{name} должно быть целым числом: {value!r}") from exc


def _env_bool(source: Mapping[str, str], name: str, default: bool) -> bool:
    """Прочитать флаг окружения: `1/true/yes/on` и `0/false/no/off`."""
    value = _clean(source.get(name))
    if value is None:
        return default
    lowered = value.lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    raise ServiceConfigError(
        f"{name} должен быть одним из: 1, 0, true, false, yes, no, on, off"
    )


def _env_float(source: Mapping[str, str], name: str, default: float) -> float:
    """Прочитать дробную переменную окружения с понятной ошибкой."""
    value = _clean(source.get(name))
    if value is None:
        return default
    try:
        return float(value)
    except ValueError as exc:
        raise ServiceConfigError(f"{name} должно быть числом: {value!r}") from exc
