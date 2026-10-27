"""Тесты QWebChannel-моста сценариев (слоты вызываются напрямую)."""

import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtWidgets import QApplication

from bridge.blockly_ir import scenario_to_workspace
from bridge.scenario_file import save_document
from bridge.web_channel import ScenarioBridge
from core.ir.nodes import ClickNode, DelayNode, LoopNode, Scenario
from gui.editor.scenario_adapter import ScenarioAdapter
from tests.test_executor import MockBackend


def wait_for(predicate: Callable[[], bool], timeout: float = 3.0) -> bool:
    """Ждать условия, прокачивая очередь событий Qt."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        QApplication.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    QApplication.processEvents()
    return predicate()


def quick_scenario() -> Scenario:
    """Короткий сценарий с известными id блоков."""
    return Scenario(
        name="Быстрый",
        nodes=(
            ClickNode(id="c1", x=5, y=6),
            DelayNode(id="d1", seconds=0.01),
        ),
    )


def endless_scenario() -> Scenario:
    """Бесконечный цикл для проверки стопа."""
    return Scenario(
        name="Вечный",
        nodes=(
            LoopNode(
                id="l1",
                times=None,
                children=(DelayNode(id="d1", seconds=0.02),),
            ),
        ),
    )


def workspace_json(scenario: Scenario) -> str:
    """JSON workspace Blockly для заданного сценария."""
    return json.dumps(scenario_to_workspace(scenario), ensure_ascii=False)


def make_bridge(
    recorder: dict[str, list[Any]] | None = None,
    **kwargs: Any,
) -> tuple[ScenarioAdapter, ScenarioBridge, dict[str, list[Any]]]:
    """Создать адаптер и мост с собранными в список сигналами."""
    if recorder is None:
        recorder = {}
    for key in (
        "nodes",
        "steps",
        "finished",
        "running",
        "loaded",
        "issues",
        "status",
        "saved",
    ):
        recorder.setdefault(key, [])
    adapter = ScenarioAdapter(MockBackend())
    bridge = ScenarioBridge(adapter, **kwargs)
    bridge.node_started.connect(recorder.setdefault("nodes", []).append)
    bridge.step_done.connect(recorder.setdefault("steps", []).append)
    bridge.run_finished.connect(
        lambda reason, message: recorder.setdefault("finished", []).append(
            (reason, message)
        )
    )
    bridge.running_changed.connect(recorder.setdefault("running", []).append)
    bridge.scenario_loaded.connect(
        lambda name, payload: recorder.setdefault("loaded", []).append(
            (name, json.loads(payload))
        )
    )
    bridge.issues_found.connect(
        lambda payload: recorder.setdefault("issues", []).append(json.loads(payload))
    )
    bridge.status_changed.connect(
        lambda text, is_error: recorder.setdefault("status", []).append(
            (text, is_error)
        )
    )
    bridge.document_saved.connect(
        lambda path, name: recorder.setdefault("saved", []).append((path, name))
    )
    return adapter, bridge, recorder


def test_run_completes_and_highlights_nodes(qt_app: object) -> None:
    """Запуск проходит, события блоков и завершения доходят до JS-стороны."""
    adapter, bridge, events = make_bridge()
    scenario = quick_scenario()

    bridge.run(scenario.name, workspace_json(scenario))

    assert wait_for(lambda: events["finished"])
    assert events["finished"][0][0] == "completed"
    assert events["nodes"][:2] == ["c1", "d1"]
    assert events["running"] == [True, False]


def test_run_rejects_empty_workspace(qt_app: object) -> None:
    """Пустой холст — ошибка без запуска, с понятным статусом."""
    adapter, bridge, events = make_bridge()

    bridge.run("Пусто", json.dumps({"blocks": {"languageVersion": 0, "blocks": []}}))

    assert events["issues"]
    assert events["issues"][0][0]["block_id"] is None
    assert "нет блоков" in events["issues"][0][0]["message"]
    assert events["status"][-1][1] is True
    assert not adapter.is_running


def test_run_rejects_broken_json(qt_app: object) -> None:
    """Повреждённый JSON от редактора — понятная ошибка."""
    adapter, bridge, events = make_bridge()

    bridge.run("Бит", "{не json")

    assert events["status"][-1][0] == "Редактор передал повреждённые данные"
    assert not adapter.is_running


def test_run_is_refused_when_simple_mode_is_busy(qt_app: object) -> None:
    """Пока простой режим кликает, сценарий не запускается."""
    _, bridge, events = make_bridge(is_busy_checker=lambda: True)

    bridge.run("Тест", workspace_json(quick_scenario()))

    assert "Другой режим" in events["status"][-1][0]
    assert events["status"][-1][1] is True
    assert not events["running"]


def test_save_creates_hybrid_file_and_reuses_path(
    qt_app: object, tmp_path: Path
) -> None:
    """Сохранение пишет IR + workspace, повторное — без диалога."""
    path = tmp_path / "out.acl.json"
    dialog_calls: list[str] = []

    def save_dialog(suggested: str) -> str:
        dialog_calls.append(suggested)
        return str(path)

    _, bridge, events = make_bridge(save_dialog=save_dialog)
    scenario = quick_scenario()

    bridge.save(scenario.name, workspace_json(scenario))
    bridge.save(scenario.name, workspace_json(scenario))

    assert len(dialog_calls) == 1
    assert path.is_file()
    assert events["saved"] == [(str(path), scenario.name)] * 2
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["name"] == scenario.name
    assert raw["editor"]["kind"] == "blockly"
    assert raw["editor"]["workspace"]["blocks"]["blocks"]
    assert [node["id"] for node in raw["nodes"]] == ["c1", "d1"]


def test_save_appends_acl_suffix(qt_app: object, tmp_path: Path) -> None:
    """Если пользователь не указал расширение, оно добавляется."""
    chosen = tmp_path / "без-расширения"

    def save_dialog(suggested: str) -> str:
        return str(chosen)

    _, bridge, events = make_bridge(save_dialog=save_dialog)
    bridge.save("Имя", workspace_json(quick_scenario()))

    expected = tmp_path / "без-расширения.acl.json"
    assert expected.is_file()
    assert len(events["saved"]) == 1


def test_save_cancelled_shows_status(qt_app: object, tmp_path: Path) -> None:
    """Отмена диалога сохранения не создаёт файл."""
    _, bridge, events = make_bridge(save_dialog=lambda suggested: None)

    bridge.save("Имя", workspace_json(quick_scenario()))

    assert not list(tmp_path.iterdir())
    assert events["status"][-1][0] == "Сохранение отменено"


def test_save_rejects_empty_workspace(qt_app: object, tmp_path: Path) -> None:
    """Пустой холст нельзя сохранить как сценарий."""
    calls: list[str] = []

    def save_dialog(suggested: str) -> str:
        calls.append(suggested)
        return str(tmp_path / "out.acl.json")

    _, bridge, events = make_bridge(save_dialog=save_dialog)
    bridge.save("Имя", json.dumps({"blocks": {"blocks": []}}))

    assert calls == []
    assert events["issues"]
    assert not list(tmp_path.iterdir())


def test_open_loads_consistent_workspace(qt_app: object, tmp_path: Path) -> None:
    """Открытие файла с сохранённым состоянием восстанавливает холст."""
    scenario = quick_scenario()
    path = tmp_path / "stored.acl.json"
    save_document(scenario, path, scenario_to_workspace(scenario))

    _, bridge, events = make_bridge(
        open_dialog=lambda: str(path),
        save_dialog=lambda suggested: None,
    )
    bridge.open()

    assert len(events["loaded"]) == 1
    name, workspace = events["loaded"][0]
    assert name == scenario.name
    assert workspace["blocks"]["blocks"][0]["id"] == "c1"
    assert "восстановлены" not in events["status"][-1][0]


def test_open_falls_back_to_ir_without_workspace(
    qt_app: object, tmp_path: Path
) -> None:
    """Файл без editor.workspace открывается построением блоков из IR."""
    scenario = quick_scenario()
    path = tmp_path / "plain.acl.json"
    save_document(scenario, path)

    _, bridge, events = make_bridge(
        open_dialog=lambda: str(path),
        save_dialog=lambda suggested: None,
    )
    bridge.open()

    assert events["loaded"]
    assert "восстановлены из IR" in events["status"][-1][0]
    assert events["loaded"][0][0] == scenario.name


def test_open_failure_shows_status(qt_app: object, tmp_path: Path) -> None:
    """Битый файл — сообщение об ошибке, рабочая область не меняется."""
    path = tmp_path / "broken.acl.json"
    path.write_text("{не json", encoding="utf-8")

    _, bridge, events = make_bridge(
        open_dialog=lambda: str(path),
        save_dialog=lambda suggested: None,
    )
    bridge.open()

    assert not events["loaded"]
    assert events["status"][-1][1] is True


def test_new_document_resets_save_path(qt_app: object, tmp_path: Path) -> None:
    """После «Нового» следующее сохранение снова спрашивает путь."""
    first = tmp_path / "first.acl.json"
    second = tmp_path / "second.acl.json"
    dialog_calls: list[str] = []

    def save_dialog(suggested: str) -> str:
        dialog_calls.append(suggested)
        return str(first if len(dialog_calls) == 1 else second)

    _, bridge, events = make_bridge(save_dialog=save_dialog)
    payload = workspace_json(quick_scenario())

    bridge.save("Имя", payload)
    bridge.new_document()
    bridge.save("Имя", payload)

    assert dialog_calls == [str(first), str(second)] or len(dialog_calls) == 2
    assert first.is_file()
    assert second.is_file()


def test_stop_interrupts_running_scenario(qt_app: object) -> None:
    """Мост останавливает сценарий, начатый через `run`."""
    adapter, bridge, events = make_bridge()

    bridge.run("Вечный", workspace_json(endless_scenario()))
    assert wait_for(lambda: adapter.is_running)
    bridge.stop()

    assert wait_for(lambda: events["finished"])
    assert events["finished"][0][0] == "stopped"
    assert events["running"] == [True, False]


def test_ready_reports_editor_ready(qt_app: object) -> None:
    """Сигнал готовности страницы доходит до статуса."""
    _, bridge, events = make_bridge()

    bridge.ready()

    assert events["status"][-1] == ("Редактор готов", False)
