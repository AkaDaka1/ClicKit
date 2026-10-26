"""Тесты интерпретатора IR (реальный ввод не выполняется)."""

import threading
import time
from typing import Any

import pytest

from core.input.backend import Button, FailsafeTriggered
from core.ir.interpreter import Interpreter, ScenarioRuntimeError
from core.ir.nodes import Scenario
from core.ir.schema import scenario_from_mapping
from tests.test_executor import MockBackend, wait_until


def make_scenario(nodes: list[dict[str, Any]]) -> Scenario:
    """Собрать проверенный сценарий из описания узлов."""
    return scenario_from_mapping({"version": 1, "nodes": nodes})


def run_in_thread(interpreter: Interpreter) -> threading.Thread:
    """Запустить интерпретатор в отдельном потоке (как воркер)."""
    thread = threading.Thread(target=interpreter.run, daemon=True)
    thread.start()
    return thread


def test_actions_executed_in_order() -> None:
    """Действия выполняются в порядке узлов, пауза не трогает бэкенд."""
    backend = MockBackend()
    interpreter = Interpreter(
        backend,
        make_scenario(
            [
                {"type": "move", "x": 1, "y": 2, "duration": 0.1},
                {"type": "click", "x": 1, "y": 2},
                {"type": "delay", "seconds": 0},
                {"type": "key", "keys": "ctrl+s"},
                {"type": "scroll", "amount": -2},
            ]
        ),
    )

    steps = interpreter.run()

    assert steps == 5
    assert [name for name, _ in backend.calls] == [
        "move_to",
        "click",
        "press_key",
        "scroll",
    ]
    assert backend.calls[0][1] == (1, 2, 0.1)
    assert backend.calls[3][1] == (-2, None, None)


def test_loop_repeats_children() -> None:
    """Цикл выполняет тело ровно `times` раз."""
    backend = MockBackend()
    interpreter = Interpreter(
        backend,
        make_scenario(
            [
                {
                    "type": "loop",
                    "times": 3,
                    "children": [{"type": "click", "x": 5, "y": 5}],
                }
            ]
        ),
    )

    assert interpreter.run() == 3
    assert len(backend.calls) == 3


def test_nested_loops_multiply() -> None:
    """Вложенные циклы перемножают число выполнений."""
    backend = MockBackend()
    interpreter = Interpreter(
        backend,
        make_scenario(
            [
                {
                    "type": "loop",
                    "times": 2,
                    "children": [
                        {
                            "type": "loop",
                            "times": 3,
                            "children": [{"type": "click", "x": 1, "y": 1}],
                        }
                    ],
                }
            ]
        ),
    )

    assert interpreter.run() == 6
    assert len(backend.calls) == 6


def test_sequence_groups_nodes() -> None:
    """`sequence` выполняет детей подряд и считается как один уровень."""
    backend = MockBackend()
    interpreter = Interpreter(
        backend,
        make_scenario(
            [
                {
                    "type": "sequence",
                    "children": [
                        {"type": "key", "keys": "a"},
                        {"type": "key", "keys": "b"},
                    ],
                },
                {"type": "click", "x": 2, "y": 3},
            ]
        ),
    )

    assert interpreter.run() == 3
    assert [name for name, _ in backend.calls] == ["press_key", "press_key", "click"]


def test_on_step_counts_and_on_node_paths() -> None:
    """Счётчик действий и события узлов приходят в правильном порядке."""
    steps: list[int] = []
    nodes_seen: list[tuple[str | None, str]] = []
    interpreter = Interpreter(
        MockBackend(),
        make_scenario(
            [
                {"type": "click", "id": "a", "x": 1, "y": 1},
                {
                    "type": "loop",
                    "id": "loop",
                    "times": 2,
                    "children": [{"type": "click", "id": "b", "x": 2, "y": 2}],
                },
            ]
        ),
        on_step=steps.append,
        on_node=lambda node, path: nodes_seen.append((node.id, path)),
    )

    assert interpreter.run() == 3
    assert steps == [1, 2, 3]
    assert [node_id for node_id, _ in nodes_seen] == ["a", "loop", "b", "loop", "b"]
    assert [path for _, path in nodes_seen] == [
        "nodes[0]",
        "nodes[1]",
        "nodes[1].children[0]",
        "nodes[1]",
        "nodes[1].children[0]",
    ]


def test_infinite_loop_stops_quickly() -> None:
    """Бесконечный цикл прерывается стопом, не дожидаясь паузы."""
    backend = MockBackend()
    interpreter = Interpreter(
        backend,
        make_scenario(
            [
                {
                    "type": "loop",
                    "times": None,
                    "children": [
                        {"type": "click", "x": 1, "y": 1},
                        {"type": "delay", "seconds": 5},
                    ],
                }
            ]
        ),
    )
    thread = run_in_thread(interpreter)

    assert wait_until(lambda: len(backend.calls) == 1)
    interpreter.stop()
    thread.join(timeout=1.0)

    assert not thread.is_alive()
    assert len(backend.calls) == 1


def test_delay_is_interruptible() -> None:
    """Пауза прерывается стопом почти сразу."""
    interpreter = Interpreter(
        MockBackend(),
        make_scenario([{"type": "delay", "seconds": 5}]),
    )
    thread = run_in_thread(interpreter)
    time.sleep(0.05)

    started = time.monotonic()
    interpreter.stop()
    thread.join(timeout=1.0)

    assert not thread.is_alive()
    assert time.monotonic() - started < 0.5


def test_stop_before_run_does_nothing() -> None:
    """Если стоп запрошен заранее, не выполняется ни один узел."""
    backend = MockBackend()
    stop = threading.Event()
    stop.set()
    interpreter = Interpreter(
        backend,
        make_scenario([{"type": "click", "x": 1, "y": 1}]),
        stop_event=stop,
    )

    assert interpreter.run() == 0
    assert backend.calls == []


def test_failsafe_is_not_wrapped() -> None:
    """`FailsafeTriggered` проходит наружу как есть."""

    class FailsafeBackend(MockBackend):
        def click(self, x: int, y: int, button: Button = Button.LEFT) -> None:
            raise FailsafeTriggered("курсор в углу экрана")

    interpreter = Interpreter(
        FailsafeBackend(),
        make_scenario([{"type": "click", "x": 0, "y": 0}]),
    )

    with pytest.raises(FailsafeTriggered, match="курсор в углу"):
        interpreter.run()


def test_backend_error_has_node_path() -> None:
    """Ошибка бэкенда оборачивается с путём узла и исходной причиной."""

    class BrokenBackend(MockBackend):
        def click(self, x: int, y: int, button: Button = Button.LEFT) -> None:
            raise RuntimeError("нет связи")

    interpreter = Interpreter(
        BrokenBackend(),
        make_scenario([{"type": "click", "x": 1, "y": 2}]),
    )

    with pytest.raises(ScenarioRuntimeError) as info:
        interpreter.run()

    assert info.value.path == "nodes[0]"
    assert "нет связи" in str(info.value)
    assert isinstance(info.value.__cause__, RuntimeError)


def test_if_node_is_rejected() -> None:
    """Зарезервированный `if` даёт понятную ошибку, а не падение."""
    interpreter = Interpreter(
        MockBackend(),
        make_scenario([{"type": "if", "condition": {"kind": "pixel"}}]),
    )

    with pytest.raises(ScenarioRuntimeError, match="не поддерживается"):
        interpreter.run()


def test_dry_run_skips_input_and_waits() -> None:
    """Dry-run не трогает бэкенд, не ждёт паузы и проходит ∞-цикл один раз."""
    backend = MockBackend()
    interpreter = Interpreter(
        backend,
        make_scenario(
            [
                {"type": "click", "x": 1, "y": 1},
                {"type": "delay", "seconds": 5},
                {
                    "type": "loop",
                    "times": None,
                    "children": [{"type": "click", "x": 2, "y": 2}],
                },
            ]
        ),
        dry_run=True,
    )

    started = time.monotonic()
    steps = interpreter.run()

    assert steps == 3
    assert backend.calls == []
    assert time.monotonic() - started < 0.5


def test_empty_scenario_has_no_steps() -> None:
    """Пустой сценарий (без узлов) завершается сразу."""
    interpreter = Interpreter(MockBackend(), Scenario(nodes=()))

    assert interpreter.run() == 0
