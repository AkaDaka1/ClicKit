"""Тесты запуска IR-сценария в фоновом потоке."""

import time
from collections.abc import Callable
from typing import Any

from core.input.backend import Button, FailsafeTriggered
from core.ir.nodes import Scenario
from core.ir.schema import scenario_from_mapping
from core.scenario_runner import ScenarioRunner
from core.worker import StopReason
from tests.test_executor import MockBackend, wait_until


def make_scenario(nodes: list[dict[str, Any]]) -> Scenario:
    """Собрать проверенный сценарий из описания узлов."""
    return scenario_from_mapping({"version": 1, "nodes": nodes})


def make_recorder() -> tuple[
    list[tuple[StopReason, str]], Callable[[StopReason, str], None]
]:
    """Собрать список вызовов `on_finish`."""
    results: list[tuple[StopReason, str]] = []

    def on_finish(reason: StopReason, detail: str) -> None:
        results.append((reason, detail))

    return results, on_finish


def test_runner_completes_and_emits_events() -> None:
    """Сценарий доходит до конца: шаги, узлы и причина COMPLETED."""
    backend = MockBackend()
    results, on_finish = make_recorder()
    steps: list[int] = []
    nodes_seen: list[str | None] = []
    runner = ScenarioRunner(
        backend,
        make_scenario(
            [
                {
                    "type": "loop",
                    "times": 2,
                    "children": [{"type": "click", "id": "c", "x": 1, "y": 1}],
                }
            ]
        ),
        on_step=steps.append,
        on_node=lambda node, path: nodes_seen.append(node.id),
        on_finish=on_finish,
    )

    runner.start()

    assert wait_until(lambda: results)
    assert results == [(StopReason.COMPLETED, "")]
    assert steps == [1, 2]
    assert nodes_seen == [None, "c", None, "c"]
    assert not runner.is_running
    assert runner.join(timeout=1.0)


def test_runner_stops_infinite_scenario() -> None:
    """Бесконечный сценарий останавливается и сообщает STOPPED."""
    backend = MockBackend()
    results, on_finish = make_recorder()
    runner = ScenarioRunner(
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
        on_finish=on_finish,
    )
    runner.start()
    assert wait_until(lambda: len(backend.calls) == 1)

    runner.stop()

    assert wait_until(lambda: results)
    assert results[0][0] is StopReason.STOPPED
    assert runner.join(timeout=1.0)


def test_runner_reports_failsafe() -> None:
    """Аварийная защита бэкенда → FAILSAFE с текстом."""

    class FailsafeBackend(MockBackend):
        def click(self, x: int, y: int, button: Button = Button.LEFT) -> None:
            raise FailsafeTriggered("курсор в углу экрана")

    results, on_finish = make_recorder()
    runner = ScenarioRunner(
        FailsafeBackend(),
        make_scenario([{"type": "click", "x": 0, "y": 0}]),
        on_finish=on_finish,
    )

    runner.start()

    assert wait_until(lambda: results)
    assert results == [(StopReason.FAILSAFE, "курсор в углу экрана")]


def test_runner_reports_error_with_path() -> None:
    """Ошибка исполнения → ERROR; в тексте есть путь до узла."""

    class BrokenBackend(MockBackend):
        def click(self, x: int, y: int, button: Button = Button.LEFT) -> None:
            raise RuntimeError("нет связи")

    results, on_finish = make_recorder()
    runner = ScenarioRunner(
        BrokenBackend(),
        make_scenario([{"type": "click", "x": 1, "y": 2}]),
        on_finish=on_finish,
    )

    runner.start()

    assert wait_until(lambda: results)
    reason, detail = results[0]
    assert reason is StopReason.ERROR
    assert "нет связи" in detail
    assert "nodes[0]" in detail


def test_runner_can_restart_after_completion() -> None:
    """После завершения сценарий можно запустить снова."""
    backend = MockBackend()
    results, on_finish = make_recorder()
    runner = ScenarioRunner(
        backend,
        make_scenario(
            [
                {
                    "type": "loop",
                    "times": 2,
                    "children": [{"type": "click", "x": 1, "y": 1}],
                }
            ]
        ),
        on_finish=on_finish,
    )

    runner.start()
    assert wait_until(lambda: len(results) == 1)
    assert runner.join(timeout=1.0)
    runner.start()
    assert wait_until(lambda: len(results) == 2)
    assert runner.join(timeout=1.0)

    assert len(backend.calls) == 4
    assert [reason for reason, _ in results] == [
        StopReason.COMPLETED,
        StopReason.COMPLETED,
    ]


def test_runner_ignores_second_start_while_running() -> None:
    """Повторный старт во время работы игнорируется."""
    backend = MockBackend()
    results, on_finish = make_recorder()
    runner = ScenarioRunner(
        backend,
        make_scenario(
            [
                {
                    "type": "loop",
                    "times": None,
                    "children": [{"type": "delay", "seconds": 5}],
                }
            ]
        ),
        on_finish=on_finish,
    )
    runner.start()
    time.sleep(0.05)

    runner.start()
    runner.stop()

    assert wait_until(lambda: results)
    assert len(results) == 1
