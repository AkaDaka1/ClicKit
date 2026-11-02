"""Тесты настроек сервиса: обязательные ключ и БД, значения и приведение."""

from __future__ import annotations

import pytest

from service.app.config import (
    DEFAULT_IDEMPOTENCY_TTL_HOURS,
    DEFAULT_MAX_BODY_BYTES,
    ServiceConfigError,
    Settings,
    load_settings,
)

#: Валидный ключ записи для тестов (≥ 16 символов).
API_KEY = "test-key-0123456789"
#: URL БД для тестов: строки достаточно, соединение не устанавливается.
DB_URL = "postgresql+psycopg://clikit:clikit@localhost:5432/clikit"
#: Минимальный валидный набор переменных окружения.
BASE_ENV = {"CLICKIT_API_KEY": API_KEY, "CLICKIT_DB_URL": DB_URL}


def test_defaults_with_required_values() -> None:
    """Минимальная конфигурация: ключ и БД заданы, остальное — по умолчанию."""
    settings = load_settings(BASE_ENV)

    assert settings.api_key == API_KEY
    assert settings.admin_api_key is None
    assert settings.db_url == DB_URL
    assert settings.max_body_bytes == DEFAULT_MAX_BODY_BYTES
    assert settings.idempotency_ttl_hours == DEFAULT_IDEMPOTENCY_TTL_HOURS
    assert settings.git_sha == "unknown"
    assert settings.build_time == ""
    assert settings.log_level == "INFO"


def test_missing_api_key_is_fail_closed() -> None:
    """Без ключа записи сервис не стартует."""
    with pytest.raises(ServiceConfigError, match="CLICKIT_API_KEY"):
        load_settings({"CLICKIT_DB_URL": DB_URL})


def test_missing_db_url_is_fail_closed() -> None:
    """Без URL БД сервис не стартует: писать сценарии некуда."""
    with pytest.raises(ServiceConfigError, match="CLICKIT_DB_URL"):
        load_settings({"CLICKIT_API_KEY": API_KEY})


def test_blank_db_url_is_not_set() -> None:
    """URL из пробелов — это отсутствие значения, а не «пустая строка»."""
    with pytest.raises(ServiceConfigError, match="CLICKIT_DB_URL"):
        load_settings({**BASE_ENV, "CLICKIT_DB_URL": "   "})


def test_short_api_key_is_rejected() -> None:
    """Короткий ключ не считается защитой."""
    with pytest.raises(ServiceConfigError, match="короче"):
        load_settings({**BASE_ENV, "CLICKIT_API_KEY": "short"})


def test_short_admin_key_is_rejected() -> None:
    """Админ-ключ проверяется той же длиной."""
    with pytest.raises(ServiceConfigError, match="CLICKIT_ADMIN_API_KEY"):
        load_settings({**BASE_ENV, "CLICKIT_ADMIN_API_KEY": "short"})


def test_empty_values_mean_not_set() -> None:
    """Пустая строка в окружении — это «не задано», а не пустой секрет."""
    settings = load_settings({**BASE_ENV, "CLICKIT_ADMIN_API_KEY": "   "})

    assert settings.admin_api_key is None


def test_values_are_read_and_normalized() -> None:
    """Строки тримятся, уровень журнала приводится к верхнему регистру."""
    settings = load_settings(
        {
            "CLICKIT_API_KEY": f"  {API_KEY}  ",
            "CLICKIT_ADMIN_API_KEY": "admin-key-0123456789",
            "CLICKIT_DB_URL": "  postgresql+psycopg://clikit:clikit@db:5432/clikit  ",
            "CLICKIT_MAX_BODY_BYTES": "2048",
            "CLICKIT_IDEMPOTENCY_TTL_HOURS": "6",
            "CLICKIT_GIT_SHA": "b42d792",
            "CLICKIT_BUILD_TIME": "2026-11-02T10:00:00Z",
            "CLICKIT_LOG_LEVEL": "debug",
        }
    )

    assert settings.api_key == API_KEY
    assert settings.admin_api_key == "admin-key-0123456789"
    assert settings.db_url == "postgresql+psycopg://clikit:clikit@db:5432/clikit"
    assert settings.max_body_bytes == 2048
    assert settings.idempotency_ttl_hours == 6
    assert settings.git_sha == "b42d792"
    assert settings.build_time == "2026-11-02T10:00:00Z"
    assert settings.log_level == "DEBUG"


def test_non_integer_value_is_reported() -> None:
    """Нечисловой лимит — ошибка конфигурации с именем переменной."""
    with pytest.raises(ServiceConfigError, match="CLICKIT_MAX_BODY_BYTES"):
        load_settings({**BASE_ENV, "CLICKIT_MAX_BODY_BYTES": "1MB"})


def test_non_positive_limits_are_rejected() -> None:
    """Нулевые лимиты ломают контракт, поэтому запрещены."""
    with pytest.raises(ServiceConfigError, match="CLICKIT_MAX_BODY_BYTES"):
        load_settings({**BASE_ENV, "CLICKIT_MAX_BODY_BYTES": "0"})
    with pytest.raises(ServiceConfigError, match="CLICKIT_IDEMPOTENCY_TTL_HOURS"):
        load_settings({**BASE_ENV, "CLICKIT_IDEMPOTENCY_TTL_HOURS": "0"})


def test_unknown_log_level_is_rejected() -> None:
    """Опечатка в уровне журнала не должна тихо превращаться в INFO."""
    with pytest.raises(ServiceConfigError, match="CLICKIT_LOG_LEVEL"):
        load_settings({**BASE_ENV, "CLICKIT_LOG_LEVEL": "verbose"})


def test_explicit_settings_validate_the_same_way() -> None:
    """`Settings.validate` доступен и для явных настроек (тесты, T4.2)."""
    Settings(api_key=API_KEY, db_url=DB_URL).validate()
    with pytest.raises(ServiceConfigError):
        Settings().validate()
