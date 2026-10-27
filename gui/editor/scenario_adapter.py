"""Qt-адаптер сценария: поток `ScenarioRunner` → сигналы GUI."""

import logging

from PySide6.QtCore import QObject, Signal

from core.input.backend import InputBackend
from core.ir.nodes import Node, Scenario
from core.scenario_runner import ScenarioRunner
from core.worker import StopReason

logger = logging.getLogger(__name__)


class ScenarioAdapter(QObject):
    """Запускает IR-сценарий и транслирует события в GUI-поток.

    Устройство повторяет `ExecutorAdapter`: у каждого прогона свой номер,
    события устаревшего прогона отбрасываются, поэтому быстрый «стоп → старт»
    не сбивает состояние интерфейса.
    """

    started = Signal()
    step = Signal(int)  # выполнено действий
    node_started = Signal(str)  # id блока (пустая строка, если id нет)
    finished = Signal(str, str)  # StopReason.value, подробности (или "")

    def __init__(
        self,
        backend: InputBackend,
        parent: QObject | None = None,
    ) -> None:
        """Создать адаптер с общим бэкендом ввода."""
        super().__init__(parent)
        self._backend = backend
        self._runner: ScenarioRunner | None = None
        self._run_id = 0

    @property
    def is_running(self) -> bool:
        """Идёт ли выполнение сценария прямо сейчас."""
        runner = self._runner
        return runner is not None and runner.is_running

    def start(self, scenario: Scenario) -> bool:
        """Запустить сценарий.

        Возвращает `False`, если сценарий уже выполняется или предыдущий
        прогон ещё не успел завершиться.
        """
        previous = self._runner
        if previous is not None:
            if previous.is_running:
                logger.debug("Повторный запуск сценария проигнорирован")
                return False
            if not previous.join(timeout=0.5):
                logger.warning("Предыдущий сценарий не завершился, запуск отложен")
                return False

        self._run_id += 1
        run_id = self._run_id
        runner = ScenarioRunner(
            self._backend,
            scenario,
            on_step=lambda count: self._emit_step(run_id, count),
            on_node=lambda node, path: self._emit_node(run_id, node),
            on_finish=lambda reason, detail: self._emit_finished(
                run_id, reason, detail
            ),
        )
        self._runner = runner
        # `started` — до старта потока, как в ExecutorAdapter: GUI успевает
        # переключиться в «работает» раньше первых событий воркера.
        self.started.emit()
        runner.start()
        return True

    def stop(self, wait: bool = False) -> None:
        """Запросить остановку; `wait=True` — дождаться завершения потока."""
        if self._runner is None:
            return
        self._runner.stop()
        if wait:
            self._runner.join(timeout=0.5)

    def _emit_step(self, run_id: int, count: int) -> None:
        """Счётчик действий — только для актуального прогона."""
        if run_id == self._run_id:
            self.step.emit(count)

    def _emit_node(self, run_id: int, node: Node) -> None:
        """Начало узла — только для актуального прогона."""
        if run_id == self._run_id:
            self.node_started.emit(node.id or "")

    def _emit_finished(self, run_id: int, reason: StopReason, detail: str) -> None:
        """Причина завершения в GUI-поток; устаревшие прогоны игнорируются."""
        if run_id != self._run_id:
            logger.debug("События устаревшего сценария %s отброшены", run_id)
            return
        self.finished.emit(reason.value, detail)
