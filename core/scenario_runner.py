"""Запуск IR-сценария в фоновом потоке с причинами завершения."""

import threading
from collections.abc import Callable

from core.input.backend import InputBackend
from core.ir.interpreter import Interpreter
from core.ir.nodes import Node, Scenario
from core.worker import StopReason, ThreadedWorker


class ScenarioRunner(ThreadedWorker):
    """Выполняет сценарий в daemon-потоке и транслирует события наружу."""

    thread_name = "clickit-scenario"

    def __init__(
        self,
        backend: InputBackend,
        scenario: Scenario,
        on_step: Callable[[int], None] | None = None,
        on_node: Callable[[Node, str], None] | None = None,
        on_finish: Callable[[StopReason, str], None] | None = None,
    ) -> None:
        """Создать запускатор сценария.

        Args:
            backend: бэкенд эмуляции ввода.
            scenario: проверенный сценарий.
            on_step: callback после каждого действия (счётчик с 1).
            on_node: callback перед выполнением узла (для подсветки в GUI).
            on_finish: callback по завершении: причина и подробности.
        """
        super().__init__(on_finish=on_finish)
        self._backend = backend
        self._scenario = scenario
        self._on_step = on_step
        self._on_node = on_node

    def _run_body(self, stop: threading.Event) -> bool:
        """Выполнить сценарий интерпретатором; `False` — прерван стопом."""
        interpreter = Interpreter(
            self._backend,
            self._scenario,
            stop_event=stop,
            on_step=self._on_step,
            on_node=self._on_node,
        )
        interpreter.run()
        return not stop.is_set()
