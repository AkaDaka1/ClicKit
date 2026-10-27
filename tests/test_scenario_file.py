"""Тесты гибридного файла сценария (IR + editor.workspace)."""

import json
from pathlib import Path
from typing import Any

import pytest

from bridge.blockly_ir import workspace_to_scenario
from bridge.scenario_file import (
    ScenarioDocument,
    load_document,
    resolve_workspace,
    save_document,
)
from core.ir.nodes import ClickNode, DelayNode, Scenario
from core.ir.schema import ScenarioValidationError
from core.ir.storage import ScenarioFileError, load_scenario


def make_scenario() -> Scenario:
    """Простой сценарий с id, совпадающими с блоками ниже."""
    return Scenario(
        name="Кириллица",
        nodes=(
            ClickNode(id="c1", x=10, y=20),
            DelayNode(id="d1", seconds=0.5),
        ),
    )


def make_workspace() -> dict[str, Any]:
    """Blockly-состояние, соответствующее `make_scenario()`."""
    return {
        "blocks": {
            "languageVersion": 0,
            "blocks": [
                {
                    "type": "ck_click",
                    "id": "c1",
                    "fields": {"X": 10, "Y": 20, "BUTTON": "left"},
                    "next": {
                        "block": {
                            "type": "ck_delay",
                            "id": "d1",
                            "fields": {"SECONDS": 0.5},
                        }
                    },
                }
            ],
        }
    }


def test_round_trip_with_workspace(tmp_path: Path) -> None:
    """Сценарий и состояние Blockly сохраняются и читаются вместе."""
    path = tmp_path / "scenario.acl.json"
    saved = save_document(make_scenario(), path, make_workspace())

    assert saved == path
    document = load_document(path)
    assert document.scenario.to_mapping() == make_scenario().to_mapping()
    assert document.workspace == make_workspace()

    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["editor"]["kind"] == "blockly"
    assert raw["editor"]["workspace"] == make_workspace()


def test_hybrid_file_is_valid_for_m3_storage(tmp_path: Path) -> None:
    """Старый API `load_scenario` читает гибридный файл как обычный IR."""
    path = tmp_path / "scenario.acl.json"
    save_document(make_scenario(), path, make_workspace())

    assert load_scenario(path).to_mapping() == make_scenario().to_mapping()


def test_save_without_workspace_has_no_editor_key(tmp_path: Path) -> None:
    """Без состояния редактора поле `editor` не добавляется."""
    path = tmp_path / "plain.acl.json"
    save_document(make_scenario(), path)

    raw = json.loads(path.read_text(encoding="utf-8"))
    assert "editor" not in raw
    assert load_document(path).workspace is None


def test_atomic_save_leaves_no_tmp_file(tmp_path: Path) -> None:
    """Временный файл после записи не остаётся."""
    path = tmp_path / "nested" / "scenario.acl.json"
    save_document(make_scenario(), path)

    assert path.is_file()
    assert not path.with_name(path.name + ".tmp").exists()


@pytest.mark.parametrize(
    "editor",
    [
        {"workspace": "нет"},
        {"workspace": 42},
        {"kind": "other", "workspace": make_workspace()},
        [],
    ],
)
def test_invalid_editor_is_ignored(tmp_path: Path, editor: object) -> None:
    """Битое или чужое состояние редактора не ломает загрузку сценария."""
    path = tmp_path / "scenario.acl.json"
    payload = make_scenario().to_mapping()
    payload["editor"] = editor
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    document = load_document(path)
    assert document.scenario.to_mapping() == make_scenario().to_mapping()
    assert document.workspace is None


def test_missing_file_raises_file_error(tmp_path: Path) -> None:
    """Отсутствующий файл — `ScenarioFileError`."""
    with pytest.raises(ScenarioFileError):
        load_document(tmp_path / "missing.acl.json")


def test_broken_json_raises_validation_error(tmp_path: Path) -> None:
    """Битый JSON — `ScenarioValidationError` с путём `$`."""
    path = tmp_path / "broken.acl.json"
    path.write_text("{не json", encoding="utf-8")

    with pytest.raises(ScenarioValidationError) as excinfo:
        load_document(path)

    assert excinfo.value.issues[0].path == "$"


def test_non_object_json_raises_validation_error(tmp_path: Path) -> None:
    """JSON-массив вместо объекта — ошибка валидации."""
    path = tmp_path / "list.acl.json"
    path.write_text("[]", encoding="utf-8")

    with pytest.raises(ScenarioValidationError):
        load_document(path)


def test_invalid_scenario_raises_validation_error(tmp_path: Path) -> None:
    """Невалидный IR в файле — ошибка валидации, а не тихий пропуск."""
    path = tmp_path / "bad.acl.json"
    path.write_text(json.dumps({"nodes": []}), encoding="utf-8")

    with pytest.raises(ScenarioValidationError):
        load_document(path)


def test_resolve_uses_consistent_workspace() -> None:
    """Совпадающее состояние Blockly используется как есть."""
    document = ScenarioDocument(make_scenario(), make_workspace())
    workspace, restored = resolve_workspace(document)

    assert restored is False
    assert workspace == make_workspace()


def test_resolve_builds_from_ir_without_workspace() -> None:
    """Без состояния редактора блоки строятся из IR."""
    document = ScenarioDocument(make_scenario())
    workspace, restored = resolve_workspace(document)

    assert restored is True
    assert workspace_to_scenario(
        workspace, document.scenario.name
    ).scenario.to_mapping() == (document.scenario.to_mapping())


def test_resolve_falls_back_when_workspace_differs() -> None:
    """Если workspace расходится с `nodes`, побеждает IR."""
    inconsistent = make_workspace()
    inconsistent["blocks"]["blocks"][0]["fields"]["X"] = 999
    document = ScenarioDocument(make_scenario(), inconsistent)

    workspace, restored = resolve_workspace(document)

    assert restored is True
    translated = workspace_to_scenario(workspace, document.scenario.name)
    assert translated.scenario.to_mapping() == document.scenario.to_mapping()


def test_resolve_falls_back_when_workspace_is_broken() -> None:
    """Невалидное состояние Blockly не мешает открыть сценарий из IR."""
    broken = {"blocks": {"languageVersion": 0, "blocks": [{"type": "unknown"}]}}
    document = ScenarioDocument(make_scenario(), broken)

    workspace, restored = resolve_workspace(document)

    assert restored is True
    translated = workspace_to_scenario(workspace, document.scenario.name)
    assert translated.scenario.to_mapping() == document.scenario.to_mapping()


def test_scenario_document_defaults() -> None:
    """Состояние редактора по умолчанию отсутствует."""
    assert ScenarioDocument(make_scenario()).workspace is None
