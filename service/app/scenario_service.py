"""Доменные операции ClicKit Cloud для сценариев.

Здесь живёт всё, что не зависит от HTTP: канонизация JSON и хэши,
проверка публикации, разбор `Idempotency-Key` и решение «создать/повторить/
отклонить». Валидация IR не дублируется — она выполняется через
`core.ir.schema.scenario_from_mapping` (ADR №37).

Интерфейс `ScenarioRepository` описан здесь же, а его SQLAlchemy-реализация —
в `service/app/repository.py`: так бизнес-логику можно проверять на подделке
без запущенной PostgreSQL.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from core.ir.schema import MAX_NAME_LENGTH, ValidationIssue, scenario_from_mapping
from service.app.models import Scenario

#: Минимальная и максимальная длина `Idempotency-Key` (`docs/api.md` §7).
MIN_IDEMPOTENCY_KEY_LENGTH = 8
MAX_IDEMPOTENCY_KEY_LENGTH = 128
#: Допустимые символы ключа идемпотентности.
_IDEMPOTENCY_KEY_RE = re.compile(r"\A[A-Za-z0-9._:-]+\Z")
#: Максимальная длина описания сценария.
MAX_DESCRIPTION_LENGTH = 2000
#: Поля, попадающие в канонический хэш тела запроса (`docs/api.md` §7).
BODY_HASH_FIELDS = ("name", "description", "scenario")


class ScenarioConflictError(RuntimeError):
    """`Idempotency-Key` уже занят: другое тело (409) или гонка запросов."""


class ScenarioRepository(Protocol):
    """Хранилище сценариев, которым пользуется бизнес-логика публикации.

    Реализация работает с одной сессией, которую открывает и закрывает
    вызывающий слой (зависимость `get_session`); `commit`/`rollback` явные,
    чтобы несколько шагов идемпотентности шли в одной транзакции.
    """

    def get(self, scenario_id: uuid.UUID) -> Scenario | None:
        """Найти сценарий по идентификатору."""
        ...

    def find_by_idempotency_key(self, key: str) -> Scenario | None:
        """Найти строку, резервирующую ключ идемпотентности."""
        ...

    def create(
        self,
        publication: ValidatedPublication,
        *,
        idempotency_key: str | None,
        idempotency_body: str | None,
    ) -> Scenario:
        """Вставить сценарий; при гонке по ключу — `ScenarioConflictError`."""
        ...

    def clear_idempotency_key(self, record: Scenario) -> None:
        """Снять резервацию с протухшей строки (пункт 5, `docs/api.md` §7)."""
        ...

    def list_page(
        self,
        *,
        limit: int,
        offset: int,
    ) -> tuple[list[Scenario], int]:
        """Вернуть страницу сценариев и полное число строк."""
        ...

    def delete(self, record: Scenario) -> None:
        """Удалить сценарий."""
        ...

    def commit(self) -> None:
        """Зафиксировать транзакцию."""
        ...

    def rollback(self) -> None:
        """Откатить транзакцию."""
        ...


def sha256_hex(payload: Any) -> str:
    """Вернуть sha256 канонического JSON значения.

    Канонизация (`sort_keys`, `ensure_ascii=False`, компактные разделители)
    делает хэш детерминированным: те же данные всегда дают тот же результат,
    поэтому хэш годится и для `ETag`, и для сравнения тел идемпотентности.

    Args:
        payload: JSON-совместимое значение (словарь, список, строка, число).

    Returns:
        Хэш в hex (64 символа нижнего регистра).
    """
    text = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical_scenario_hash(document: Mapping[str, Any]) -> str:
    """Хэш канонического JSON `Scenario.to_mapping()` (`docs/api.md` §8).

    Args:
        document: Нормализованный IR-словарь (`scenario.to_mapping()`).

    Returns:
        Хэш в hex — он же значение `ETag` и колонки `sha256`.
    """
    return sha256_hex(dict(document))


def request_body_hash(body: Mapping[str, Any]) -> str:
    """Хэш канонического тела запроса публикации (`docs/api.md` §7).

    Сравниваются только поля `name`, `description`, `scenario`: прочие ключи
    тела на смысл публикации не влияют.

    Args:
        body: Разобранное тело `POST /v1/scenarios`.

    Returns:
        Хэш в hex для колонки `idempotency_body`.
    """
    subset = {field: body.get(field) for field in BODY_HASH_FIELDS}
    return sha256_hex(subset)


def normalize_idempotency_key(raw: str | None) -> str | None:
    """Проверить `Idempotency-Key` и убрать крайние пробелы.

    Args:
        raw: Значение заголовка или `None`, если заголовка нет.

    Returns:
        Ключ без крайних пробелов или `None`, если заголовок не задан.

    Raises:
        ValueError: Ключ не подходит по длине или составу символов.
    """
    if raw is None:
        return None
    key = raw.strip()
    if not key:
        return None
    if not MIN_IDEMPOTENCY_KEY_LENGTH <= len(key) <= MAX_IDEMPOTENCY_KEY_LENGTH:
        raise ValueError(
            f"Idempotency-Key должен быть от {MIN_IDEMPOTENCY_KEY_LENGTH} "
            f"до {MAX_IDEMPOTENCY_KEY_LENGTH} символов"
        )
    if _IDEMPOTENCY_KEY_RE.match(key) is None:
        raise ValueError("Idempotency-Key содержит недопустимые символы")
    return key


@dataclass(frozen=True)
class ValidatedPublication:
    """Проверенная публикация: метаданные и нормализованный IR.

    Attributes:
        name: Имя сценария (1–200 символов).
        description: Описание (может быть пустым).
        ir: Нормализованный IR (`Scenario.to_mapping()`).
        sha256: Канонический хэш IR — значение `ETag` и колонки `sha256`.
    """

    name: str
    description: str
    ir: dict[str, Any]
    sha256: str


class PublicationValidationError(ValueError):
    """Публикация не прошла проверку: содержит список путей и сообщений."""

    def __init__(self, issues: list[dict[str, str]]) -> None:
        """Сохранить ошибки валидации в формате problem+json.

        Args:
            issues: Список `{path, message}` (порядок сохраняется).
        """
        self.issues = issues
        super().__init__(f"Ошибок валидации: {len(issues)}")


def build_publication(
    *,
    name: str | None,
    description: str | None,
    scenario: Any,
) -> ValidatedPublication:
    """Проверить и нормализовать публикацию сценария.

    Имя берётся из тела запроса, а при отсутствии — из самого IR; пустое имя
    в обоих местах считается ошибкой (`docs/api.md` §5.5). IR проверяется тем
    же кодом, что и desktop-приложение (`core.ir.schema`, ADR №37).

    Args:
        name: Значение поля `name` тела (или `None`).
        description: Значение поля `description` тела (или `None`).
        scenario: Значение поля `scenario` тела (обычно словарь).

    Returns:
        Проверенная публикация с нормализованным IR и хэшем.

    Raises:
        PublicationValidationError: Есть ошибки в имени/описании/IR.
    """
    issues: list[dict[str, str]] = []
    resolved_name = _resolve_name(name, scenario, issues)
    resolved_description = _resolve_description(description, issues)

    if not isinstance(scenario, Mapping):
        issues.append(
            {"path": "scenario", "message": "должно быть JSON-объектом IR-сценария"}
        )
        raise PublicationValidationError(issues)

    normalized = _normalize_scenario(scenario, issues)
    if issues:
        raise PublicationValidationError(issues)

    return ValidatedPublication(
        name=resolved_name,
        description=resolved_description,
        ir=normalized,
        sha256=canonical_scenario_hash(normalized),
    )


def publish(
    repository: ScenarioRepository,
    publication: ValidatedPublication,
    *,
    idempotency_key: str | None,
    idempotency_body: str,
    ttl_hours: int,
    now: datetime | None = None,
) -> tuple[Scenario, bool]:
    """Создать сценарий с учётом `Idempotency-Key` (`docs/api.md` §7).

    Порядок повторяет контракт: нет ключа — обычное создание; ключ есть —
    повтор с тем же телом возвращает созданную строку (replay), с другим —
    `ScenarioConflictError`; протухшая резервация снимается и строка
    создаётся заново. Гонка двух запросов ловится уникальным индексом и
    превращается в replay или конфликт, а не в 500.

    Args:
        repository: Хранилище сценариев (SQL или подделка в тестах).
        publication: Проверенная публикация.
        idempotency_key: Ключ из заголовка или `None`.
        idempotency_body: Хэш тела запроса для сравнения повторов.
        ttl_hours: Срок жизни резервации в часах.
        now: Текущее время (тесты); по умолчанию — UTC сейчас.

    Returns:
        Кортеж `(строка, replay)`: `replay=True` — сценарий уже существовал.

    Raises:
        ScenarioConflictError: Ключ занят другим телом запроса.
    """
    moment = now if now is not None else datetime.now(UTC)

    if idempotency_key is not None:
        existing = repository.find_by_idempotency_key(idempotency_key)
        if existing is not None:
            if _reservation_is_fresh(existing, ttl_hours, moment):
                _ensure_same_body(existing, idempotency_body)
                return existing, True
            repository.clear_idempotency_key(existing)

    try:
        record = repository.create(
            publication,
            idempotency_key=idempotency_key,
            idempotency_body=idempotency_body if idempotency_key else None,
        )
        repository.commit()
        return record, False
    except ScenarioConflictError:
        repository.rollback()
        if idempotency_key is None:
            raise
        existing = repository.find_by_idempotency_key(idempotency_key)
        if existing is None:
            raise
        _ensure_same_body(existing, idempotency_body)
        return existing, True


def _reservation_is_fresh(record: Scenario, ttl_hours: int, now: datetime) -> bool:
    """Не протухла ли резервация `Idempotency-Key` (по `created_at`)."""
    created = record.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    return now - created <= timedelta(hours=ttl_hours)


def _ensure_same_body(record: Scenario, idempotency_body: str) -> None:
    """Разрешить повтор только с тем же телом запроса (иначе 409)."""
    if (record.idempotency_body or "") != idempotency_body:
        raise ScenarioConflictError(
            "Idempotency-Key уже использован с другим телом запроса"
        )


def _resolve_name(
    name: str | None,
    scenario: Any,
    issues: list[dict[str, str]],
) -> str:
    """Определить имя сценария: из тела, иначе из IR."""
    if name is not None:
        value = name.strip()
        if not value:
            issues.append({"path": "name", "message": "не может быть пустым"})
            return ""
        if len(value) > MAX_NAME_LENGTH:
            issues.append(
                {
                    "path": "name",
                    "message": f"должно быть не длиннее {MAX_NAME_LENGTH} символов",
                }
            )
            return ""
        return value
    if isinstance(scenario, Mapping):
        inner = scenario.get("name")
        if isinstance(inner, str) and inner.strip():
            return inner.strip()
    issues.append(
        {"path": "name", "message": "укажите name или непустое имя в scenario"}
    )
    return ""


def _resolve_description(
    description: str | None,
    issues: list[dict[str, str]],
) -> str:
    """Проверить необязательное описание."""
    if description is None:
        return ""
    if len(description) > MAX_DESCRIPTION_LENGTH:
        issues.append(
            {
                "path": "description",
                "message": f"должно быть не длиннее {MAX_DESCRIPTION_LENGTH} символов",
            }
        )
        return ""
    return description


def _normalize_scenario(
    scenario: Mapping[str, Any],
    issues: list[dict[str, str]],
) -> dict[str, Any]:
    """Проверить IR через `core.ir.schema` и вернуть канонический словарь."""
    from core.ir.schema import ScenarioValidationError

    try:
        parsed = scenario_from_mapping(scenario)
    except ScenarioValidationError as exc:
        issues.extend(_issue_dicts(exc.issues))
        return {}
    return parsed.to_mapping()


def _issue_dicts(issues: tuple[ValidationIssue, ...]) -> list[dict[str, str]]:
    """Преобразовать `ValidationIssue` в словари `{path, message}`."""
    return [{"path": issue.path, "message": issue.message} for issue in issues]
