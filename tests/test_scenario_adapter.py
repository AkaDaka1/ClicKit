"""Тесты адаптера сценария (mock-бэкенд, без реального ввода)."""

import time
from collections.abc import Callable

from PySide6.QtWidgets import QApplication

from core.input.backend import Button, FailsafeTriggered
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
    """Короткий сценарий: клик и маленькая пауза."""
    return Scenario(
        name="Быстрый",
        nodes=(
            ClickNode(id="c1", x=5, y=6),
            DelayNode(id="d1", seconds=0.01),
        ),
    )


def endless_scenario() -> Scenario:
    """Бесконечный цикл с паузой — для проверки стопа."""
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


class FailsafeBackend(MockBackend):
    """Бэкенд, на котором срабатывает аварийная защита."""

    def click(self, x: int, y: int, button: Button = Button.LEFT) -> None:
        """Имитировать курсор в аварийном углу."""
        raise FailsafeTriggered("курсор в углу экрана")


class ErrorBackend(MockBackend):
    """Бэкенд, который падает при клике."""

    def click(self, x: int, y: int, button: Button = Button.LEFT) -> None:
        """Имитировать сбой эмуляции ввода."""
        raise RuntimeError("драйвер ввода недоступен")


def test_completed_run_emits_nodes_and_steps(qt_app: object) -> None:
    """Успешный прогон: узлы, счётчик действий и причина завершения."""
    adapter = ScenarioAdapter(MockBackend())
    finished: list[tuple[str, str]] = []
    node_ids: list[str] = []
    steps: list[int] = []
    adapter.finished.connect(lambda reason, detail: finished.append((reason, detail)))
    adapter.node_started.connect(node_ids.append)
    adapter.step.connect(steps.append)

    assert adapter.start(quick_scenario()) is True
    assert wait_for(lambda: finished)

    assert finished == [("completed", "")]
    assert node_ids == ["c1", "d1"]
    assert steps == [1, 2]
    assert adapter.is_running is False


def test_stop_interrupts_endless_loop(qt_app: object) -> None:
    """Бесконечный цикл останавливается и сообщает причину STOPPED."""
    adapter = ScenarioAdapter(MockBackend())
    finished: list[str] = []
    adapter.finished.connect(lambda reason, detail: finished.append(reason))

    adapter.start(endless_scenario())
    assert wait_for(lambda: adapter.is_running)
    adapter.stop()

    assert wait_for(lambda: finished)
    assert finished == ["stopped"]


def test_failsafe_reason_passes_through(qt_app: object) -> None:
    """Аварийная защита бэкенда превращается в причину FAILSAFE."""
    adapter = ScenarioAdapter(FailsafeBackend())
    finished: list[tuple[str, str]] = []
    adapter.finished.connect(lambda reason, detail: finished.append((reason, detail)))

    adapter.start(quick_scenario())
    assert wait_for(lambda: finished)

    assert finished[0][0] == "failsafe"
    assert "углу" in finished[0][1]


def test_backend_error_reports_error(qt_app: object) -> None:
    """Сбой бэкенда — причина ERROR с понятным текстом."""
    adapter = ScenarioAdapter(ErrorBackend())
    finished: list[tuple[str, str]] = []
    adapter.finished.connect(lambda reason, detail: finished.append((reason, detail)))

    adapter.start(quick_scenario())
    assert wait_for(lambda: finished)

    assert finished[0][0] == "error"
    assert "драйвер ввода недоступен" in finished[0][1]


def test_second_start_is_refused_while_running(qt_app: object) -> None:
    """Повторный запуск во время выполнения отклоняется."""
    adapter = ScenarioAdapter(MockBackend())

    assert adapter.start(endless_scenario()) is True
    assert wait_for(lambda: adapter.is_running)
    assert adapter.start(quick_scenario()) is False

    adapter.stop(wait=True)


def test_adapter_can_restart_after_finish(qt_app: object) -> None:
    """После завершения адаптер готов к новому прогону."""
    adapter = ScenarioAdapter(MockBackend())
    finished: list[str] = []
    adapter.finished.connect(lambda reason, detail: finished.append(reason))

    assert adapter.start(quick_scenario()) is True
    assert wait_for(lambda: len(finished) == 1)
    assert adapter.start(quick_scenario()) is True
    assert wait_for(lambda: len(finished) == 2)
    assert finished == ["completed", "completed"]
