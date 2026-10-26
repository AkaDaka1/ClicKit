"""Тесты сохранения и загрузки сценариев `.acl.json`."""

import json
from pathlib import Path

import pytest

from core.ir.nodes import Scenario
from core.ir.schema import ScenarioValidationError, scenario_from_mapping
from core.ir.storage import (
    SCENARIO_SUFFIX,
    ScenarioFileError,
    default_scenarios_dir,
    load_scenario,
    save_scenario,
)


def make_scenario() -> Scenario:
    """Небольшой сценарий с кириллическим именем и циклом."""
    return scenario_from_mapping(
        {
            "version": 1,
            "name": "Проверка сохранения",
            "nodes": [
                {"type": "click", "id": "start", "x": 10, "y": 20},
                {
                    "type": "loop",
                    "times": 2,
                    "children": [{"type": "delay", "seconds": 0.1}],
                },
            ],
        }
    )


def test_save_and_load_round_trip(tmp_path: Path) -> None:
    """Сценарий сохраняется и читается без потерь, кириллица — как есть."""
    scenario = make_scenario()
    path = tmp_path / f"demo{SCENARIO_SUFFIX}"

    saved = save_scenario(scenario, path)

    assert saved == path
    assert load_scenario(path) == scenario
    raw = path.read_text(encoding="utf-8")
    assert "Проверка сохранения" in raw
    assert not path.with_name(path.name + ".tmp").exists()
    payload = json.loads(raw)
    assert payload["version"] == 1
    assert payload["nodes"][1]["times"] == 2


def test_save_creates_parent_directories(tmp_path: Path) -> None:
    """Отсутствующие каталоги создаются при сохранении."""
    path = tmp_path / "scenarios" / "nested" / "demo.acl.json"

    save_scenario(make_scenario(), path)

    assert path.is_file()


def test_load_missing_file(tmp_path: Path) -> None:
    """Отсутствующий файл — понятная ошибка файла."""
    with pytest.raises(ScenarioFileError, match="Не удалось прочитать"):
        load_scenario(tmp_path / "missing.acl.json")


def test_load_broken_json(tmp_path: Path) -> None:
    """Битый JSON — ошибка валидации с указанием места."""
    path = tmp_path / "broken.acl.json"
    path.write_text("{ не json", encoding="utf-8")

    with pytest.raises(ScenarioValidationError) as info:
        load_scenario(path)

    assert info.value.issues[0].path == "$"


def test_load_non_object_json(tmp_path: Path) -> None:
    """JSON-массив вместо объекта — ошибка валидации."""
    path = tmp_path / "array.acl.json"
    path.write_text("[]", encoding="utf-8")

    with pytest.raises(ScenarioValidationError, match="JSON-объектом"):
        load_scenario(path)


def test_load_invalid_scenario(tmp_path: Path) -> None:
    """Семантически неверный сценарий не загружается."""
    path = tmp_path / "invalid.acl.json"
    path.write_text(
        json.dumps({"version": 1, "nodes": [{"type": "nope"}]}),
        encoding="utf-8",
    )

    with pytest.raises(ScenarioValidationError, match="неизвестный тип"):
        load_scenario(path)


def test_save_reports_unwritable_path(tmp_path: Path) -> None:
    """Ошибка записи заворачивается в `ScenarioFileError`."""
    directory = tmp_path / "as-directory"
    directory.mkdir()

    with pytest.raises(ScenarioFileError, match="Не удалось сохранить"):
        save_scenario(make_scenario(), directory)


def test_default_scenarios_dir_uses_appdata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Каталог по умолчанию строится от `%APPDATA%`."""
    monkeypatch.setenv("APPDATA", str(tmp_path))

    assert default_scenarios_dir() == tmp_path / "ClicKit" / "scenarios"
