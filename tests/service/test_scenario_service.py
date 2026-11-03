"""Тесты чистого доменного слоя сценариев (`service/app/scenario_service.py`).

Проверяются канонические хэши, разбор `Idempotency-Key` и валидация
публикации через `core.ir.schema` (ADR №37) — без HTTP и без БД.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from service.app.scenario_service import (
    BODY_HASH_FIELDS,
    MAX_DESCRIPTION_LENGTH,
    MAX_IDEMPOTENCY_KEY_LENGTH,
    MIN_IDEMPOTENCY_KEY_LENGTH,
    PublicationValidationError,
    build_publication,
    canonical_scenario_hash,
    normalize_idempotency_key,
    request_body_hash,
    sha256_hex,
)

pytest.importorskip("sqlalchemy")

#: Простейший валидный IR.
SIMPLE_IR = {
    "version": 1,
    "name": "demo",
    "nodes": [{"type": "click", "x": 10, "y": 20}],
}


def test_sha256_hex_matches_manual_canonical_json() -> None:
    """Хэш совпадает с ручным расчётом канонического JSON (§8)."""
    payload = {"b": 1, "a": [2, {"z": "ю"}]}
    expected = hashlib.sha256(
        json.dumps(
            payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()

    assert sha256_hex(payload) == expected
    assert len(expected) == 64


def test_sha256_hex_ignores_key_order() -> None:
    """Порядок ключей не влияет на хэш — повтор публикации детерминирован."""
    assert sha256_hex({"x": 1, "y": 2}) == sha256_hex({"y": 2, "x": 1})


def test_sha256_hex_hashes_non_ascii_as_utf8() -> None:
    """Кириллица хэшируется как UTF-8, а не как `\\uXXXX`-экранирование."""
    manual = hashlib.sha256('{"name":"клик"}'.encode()).hexdigest()

    assert sha256_hex({"name": "клик"}) == manual


def test_canonical_scenario_hash_uses_normalized_document() -> None:
    """Хэш сценария — от нормализованного IR (`Scenario.to_mapping()`)."""
    publication = build_publication(name=None, description=None, scenario=SIMPLE_IR)

    assert publication.sha256 == canonical_scenario_hash(publication.ir)
    assert publication.ir["nodes"][0]["button"] == "left"


def test_request_body_hash_uses_contract_fields_only() -> None:
    """В хэш тела попадают только `name`/`description`/`scenario` (§7)."""
    assert BODY_HASH_FIELDS == ("name", "description", "scenario")
    base = {"name": "demo", "description": "", "scenario": SIMPLE_IR}
    with_extra = {**base, "unknown": "игнорируется"}

    assert request_body_hash(base) == request_body_hash(with_extra)


def test_request_body_hash_differs_for_other_body() -> None:
    """Другое описание даёт другой хэш — основа 409 при конфликте."""
    first = {"name": "demo", "description": "", "scenario": SIMPLE_IR}
    second = {**first, "description": "иное"}

    assert request_body_hash(first) != request_body_hash(second)


@pytest.mark.parametrize(
    "key",
    [
        "demo-key",
        "a1b2c3d4",
        "key.with:dots-and_colon",
        "k" * MAX_IDEMPOTENCY_KEY_LENGTH,
    ],
)
def test_normalize_idempotency_key_accepts_valid(key: str) -> None:
    """Допустимые символы `[A-Za-z0-9._:-]` принимаются (§7)."""
    assert normalize_idempotency_key(key) == key


def test_normalize_idempotency_key_strips_whitespace() -> None:
    """Крайние пробелы заголовка не влияют на ключ."""
    assert normalize_idempotency_key("  demo-key-1  ") == "demo-key-1"


@pytest.mark.parametrize("key", [None, "", "   "])
def test_normalize_idempotency_key_absent(key: str | None) -> None:
    """Отсутствие ключа — обычное создание без резервации (§7, п. 1)."""
    assert normalize_idempotency_key(key) is None


def test_normalize_idempotency_key_rejects_short() -> None:
    """Ключ короче минимума отклоняется."""
    with pytest.raises(ValueError, match=str(MIN_IDEMPOTENCY_KEY_LENGTH)):
        normalize_idempotency_key("abc")


def test_normalize_idempotency_key_rejects_long() -> None:
    """Ключ длиннее максимума отклоняется."""
    with pytest.raises(ValueError, match=str(MAX_IDEMPOTENCY_KEY_LENGTH)):
        normalize_idempotency_key("k" * (MAX_IDEMPOTENCY_KEY_LENGTH + 1))


def test_normalize_idempotency_key_rejects_illegal_characters() -> None:
    """Пробелы и спецсимволы внутри ключа недопустимы."""
    with pytest.raises(ValueError, match="недопустимые символы"):
        normalize_idempotency_key("key with space")


def test_build_publication_uses_scenario_name_when_absent() -> None:
    """Без `name` в теле имя берётся из IR (§5.5)."""
    publication = build_publication(name=None, description=None, scenario=SIMPLE_IR)

    assert publication.name == "demo"
    assert publication.description == ""


def test_build_publication_prefers_explicit_name() -> None:
    """Явное `name` важнее имени внутри IR."""
    publication = build_publication(
        name="  явное  ", description=None, scenario=SIMPLE_IR
    )

    assert publication.name == "явное"


def test_build_publication_normalizes_nested_nodes() -> None:
    """Вложенные узлы нормализуются с сохранением `id` и дефолтов."""
    ir = {
        "version": 1,
        "name": "demo",
        "nodes": [
            {
                "type": "loop",
                "id": "main",
                "times": 2,
                "children": [{"type": "move", "id": "m1", "x": 1, "y": 2}],
            }
        ],
    }

    publication = build_publication(name=None, description=None, scenario=ir)

    loop = publication.ir["nodes"][0]
    assert loop["id"] == "main"
    assert loop["children"][0]["duration"] == 0.0


def test_missing_name_everywhere_is_rejected() -> None:
    """Ни в теле, ни в IR нет имени — ошибка с путём `name`."""
    scenario = {"version": 1, "nodes": [{"type": "click", "x": 1, "y": 1}]}

    with pytest.raises(PublicationValidationError) as exc_info:
        build_publication(name=None, description=None, scenario=scenario)

    assert [issue["path"] for issue in exc_info.value.issues] == ["name"]


def test_blank_name_is_rejected() -> None:
    """Пустое имя в теле — ошибка, а не молчаливый дефолт."""
    with pytest.raises(PublicationValidationError) as exc_info:
        build_publication(name="   ", description=None, scenario=SIMPLE_IR)

    assert exc_info.value.issues[0]["path"] == "name"


def test_too_long_name_is_rejected() -> None:
    """Имя длиннее 200 символов отклоняется (лимит `core.ir.schema`)."""
    with pytest.raises(PublicationValidationError) as exc_info:
        build_publication(name="a" * 201, description=None, scenario=SIMPLE_IR)

    assert exc_info.value.issues[0]["path"] == "name"


def test_too_long_description_is_rejected() -> None:
    """Описание длиннее лимита отклоняется."""
    with pytest.raises(PublicationValidationError) as exc_info:
        build_publication(
            name="demo",
            description="д" * (MAX_DESCRIPTION_LENGTH + 1),
            scenario=SIMPLE_IR,
        )

    assert exc_info.value.issues[0]["path"] == "description"


def test_non_mapping_scenario_is_rejected() -> None:
    """`scenario` не объект — ошибка с путём `scenario`."""
    with pytest.raises(PublicationValidationError) as exc_info:
        build_publication(name="demo", description=None, scenario=[1, 2])

    assert exc_info.value.issues[0]["path"] == "scenario"


def test_ir_errors_come_from_core_schema() -> None:
    """Пути ошибок IR берутся напрямую из `core.ir.schema` (§4)."""
    scenario = {
        "version": 1,
        "name": "demo",
        "nodes": [{"type": "click", "x": 1}, {"type": "teleport"}],
    }

    with pytest.raises(PublicationValidationError) as exc_info:
        build_publication(name=None, description=None, scenario=scenario)

    paths = {issue["path"] for issue in exc_info.value.issues}
    assert "nodes[0].y" in paths
    assert "nodes[1]" in paths


def test_all_issues_are_collected_at_once() -> None:
    """Ошибки имени и IR возвращаются одним списком, а не по очереди."""
    scenario = {"version": 2, "nodes": []}

    with pytest.raises(PublicationValidationError) as exc_info:
        build_publication(name=None, description=None, scenario=scenario)

    paths = {issue["path"] for issue in exc_info.value.issues}
    assert {"name", "version", "nodes"} <= paths


def test_unknown_ir_keys_are_ignored() -> None:
    """Неизвестные ключи IR игнорируются — совместимость вперёд (§6)."""
    scenario = {**SIMPLE_IR, "future_field": True}

    publication = build_publication(name=None, description=None, scenario=scenario)

    assert "future_field" not in publication.ir
