"""Доменные операции ClicKit Cloud для crash-отчётов.

Здесь живёт санитайзер traceback (`docs/api.md` §5.9): домашние каталоги
заменяются на `<пользователь>`, текст обрезается до 16 КБ. Правило одно
и тестируется в `tests/service/test_crash_service.py`; сервер **не логирует**
тело отчёта и не пишет IP клиента (ADR №38).

Ретеншн: отчёты хранятся 30 дней (политика документирована; фоновый
очиститель — M8/M11, вне рамок этой задачи).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: Максимальный размер traceback после санитизации (кодовые точки, `docs/api.md` §5.9).
MAX_TRACEBACK_LENGTH = 16_384
#: Максимальные длины полей по контракту (`docs/api.md` §5.9).
MAX_APP_VERSION_LENGTH = 64
MAX_OS_LENGTH = 64
#: Регулярка для error_hash: ровно 64 hex-символа нижнего регистра.
_ERROR_HASH_RE = re.compile(r"\A[0-9a-f]{64}\Z")
#: Шаблоны домашних каталогов (Windows + Unix). Заменяются на `<пользователь>`.
_HOME_PATTERNS: tuple[re.Pattern[str], ...] = (
    # Windows: `C:\Users\<имя>\` и `C:/Users/<имя>/` (и другие диски).
    re.compile(r"[A-Za-z]:[/\\]Users[/\\][^/\\]+(?=[/\\]|\Z)", re.IGNORECASE),
    # Unix: `/home/<имя>` и `/Users/<имя>` (macOS).
    re.compile(r"/(?:home|Users)/[^/]+(?=/|\Z)"),
)
#: Маркер замены домашнего каталога в санитизированном traceback.
HOME_REPLACEMENT = "<пользователь>"


@dataclass(frozen=True)
class ValidatedCrashReport:
    """Проверенный crash-отчёт: поля уже соответствуют лимитам контракта.

    Attributes:
        app_version: Версия desktop-приложения (1–64 символа).
        os: Описание ОС (может быть пустым).
        error_hash: sha256 сигнатуры ошибки (64 hex-символа).
        traceback: Санитизированный traceback (пустая строка, если не передан).
    """

    app_version: str
    os: str
    error_hash: str
    traceback: str


class CrashReportValidationError(ValueError):
    """Crash-отчёт не прошёл проверку: содержит список путей и сообщений."""

    def __init__(self, issues: list[dict[str, str]]) -> None:
        """Сохранить ошибки валидации в формате problem+json.

        Args:
            issues: Список `{path, message}` (порядок сохраняется).
        """
        self.issues = issues
        super().__init__(f"Ошибок валидации crash-отчёта: {len(issues)}")


def sanitize_traceback(text: str | None) -> str:
    """Очистить traceback от PII и обрезать до 16 КБ (`docs/api.md` §5.9).

    Домашние каталоги `C:\\Users\\<имя>\\`, `/home/<имя>/` и `/Users/<имя>/`
    заменяются на `<пользователь>`; после замены текст обрезается по кодовым
    точкам (не байтам), чтобы не порвать многобайтовую последовательность.

    Args:
        text: Исходный traceback или `None`.

    Returns:
        Санитизированный текст или пустая строка, если вход был `None`/пуст.
    """
    if text is None:
        return ""
    cleaned = text.strip()
    if not cleaned:
        return ""
    for pattern in _HOME_PATTERNS:
        cleaned = pattern.sub(HOME_REPLACEMENT, cleaned)
    if len(cleaned) > MAX_TRACEBACK_LENGTH:
        cleaned = cleaned[:MAX_TRACEBACK_LENGTH]
    return cleaned


def build_crash_report(
    *,
    app_version: str | None,
    os: str | None,
    error_hash: str | None,
    traceback: str | None,
) -> ValidatedCrashReport:
    """Проверить и нормализовать crash-отчёт.

    Все поля проверяются по контракту `docs/api.md` §5.9; ошибки собираются
    одним списком, чтобы клиент увидел всё сразу.

    Args:
        app_version: Версия desktop-приложения.
        os: Описание ОС (может отсутствовать).
        error_hash: sha256 сигнатуры ошибки.
        traceback: Трассировка (может отсутствовать; санитайзится).

    Returns:
        Проверенный отчёт с обрезанными/санитизированными полями.

    Raises:
        CrashReportValidationError: Есть ошибки валидации.
    """
    issues: list[dict[str, str]] = []
    resolved_version = _validate_app_version(app_version, issues)
    resolved_os = _validate_os(os, issues)
    resolved_hash = _validate_error_hash(error_hash, issues)
    resolved_traceback = sanitize_traceback(traceback)
    if issues:
        raise CrashReportValidationError(issues)
    return ValidatedCrashReport(
        app_version=resolved_version,
        os=resolved_os,
        error_hash=resolved_hash,
        traceback=resolved_traceback,
    )


def _validate_app_version(
    value: str | None,
    issues: list[dict[str, str]],
) -> str:
    """Проверить `app_version`: обязательное, 1–64 символа."""
    if value is None:
        issues.append({"path": "app_version", "message": "обязательное поле"})
        return ""
    stripped = value.strip()
    if not stripped:
        issues.append({"path": "app_version", "message": "не может быть пустым"})
        return ""
    if len(stripped) > MAX_APP_VERSION_LENGTH:
        issues.append(
            {
                "path": "app_version",
                "message": f"длиннее {MAX_APP_VERSION_LENGTH} символов",
            }
        )
        return ""
    return stripped


def _validate_os(value: str | None, issues: list[dict[str, str]]) -> str:
    """Проверить `os`: необязательное, до 64 символов."""
    if value is None:
        return ""
    if len(value) > MAX_OS_LENGTH:
        issues.append({"path": "os", "message": f"длиннее {MAX_OS_LENGTH} символов"})
        return ""
    return value


def _validate_error_hash(
    value: str | None,
    issues: list[dict[str, str]],
) -> str:
    """Проверить `error_hash`: обязательное, ровно 64 hex-символа."""
    if value is None:
        issues.append({"path": "error_hash", "message": "обязательное поле"})
        return ""
    stripped = value.strip().lower()
    if not _ERROR_HASH_RE.match(stripped):
        issues.append(
            {
                "path": "error_hash",
                "message": "должно быть 64 hex-символа [0-9a-f]",
            }
        )
        return ""
    return stripped
