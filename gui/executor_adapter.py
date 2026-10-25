"""Qt-адаптер исполнителя: поток воркера → сигналы GUI."""

import logging

from PySide6.QtCore import QObject, Signal

from core.executor import Executor, StopReason
from core.input.backend import InputBackend, create_backend
from gui.simple_mode.config import SimpleRunConfig

logger = logging.getLogger(__name__)


class ExecutorAdapter(QObject):
    """Запускает `Executor` по параметрам простого режима и транслирует события.

    Все сигналы приходят в GUI-поток (Qt ставит их в очередь, если испускание
    произошло в потоке исполнителя). События предыдущего прогона, пришедшие
    после нового запуска, отбрасываются по номеру прогона.
    """

    started = Signal()
    step = Signal(int)  # выполнено кликов
    finished = Signal(str, str)  # StopReason.value, подробности (или "")

    def __init__(
        self,
        backend: InputBackend | None = None,
        parent: QObject | None = None,
    ) -> None:
        """Создать адаптер; `backend=None` — бэкенд по умолчанию (pyautogui)."""
        super().__init__(parent)
        self._backend = backend if backend is not None else create_backend()
        self._executor: Executor | None = None
        self._run_id = 0

    @property
    def backend(self) -> InputBackend:
        """Бэкенд ввода (пикеру нужен для чтения позиции курсора)."""
        return self._backend

    @property
    def is_running(self) -> bool:
        """Идёт ли исполнение прямо сейчас."""
        executor = self._executor
        return executor is not None and executor.is_running

    def start(self, config: SimpleRunConfig) -> bool:
        """Запустить клики.

        Возвращает `False`, если уже выполняется или предыдущий прогон
        ещё не успел завершиться.
        """
        previous = self._executor
        if previous is not None:
            if previous.is_running:
                logger.debug("Повторный старт проигнорирован: клики уже выполняются")
                return False
            # Остановка запрошена, но поток ещё дорабатывает текущий шаг.
            if not previous.join(timeout=0.5):
                logger.warning("Предыдущий прогон не завершился, запуск отложен")
                return False

        self._run_id += 1
        run_id = self._run_id
        executor = Executor(
            self._backend,
            config.commands(),
            interval=config.interval_seconds,
            repeats=config.repeats,
            on_step=lambda count: self._emit_step(run_id, count),
            on_finish=lambda reason, detail: self._emit_finished(
                run_id, reason, detail
            ),
        )
        # `started` испускается до запуска потока — GUI успевает переключиться
        # в режим «работает» раньше, чем придут первые события воркера.
        self._executor = executor
        self.started.emit()
        executor.start()
        return True

    def stop(self, wait: bool = False) -> None:
        """Запросить остановку; `wait=True` — дождаться завершения потока."""
        if self._executor is None:
            return
        self._executor.stop()
        if wait:
            self._executor.join(timeout=0.5)

    def _emit_step(self, run_id: int, count: int) -> None:
        """Счётчик шагов — только для актуального прогона."""
        if run_id == self._run_id:
            self.step.emit(count)

    def _emit_finished(self, run_id: int, reason: StopReason, detail: str) -> None:
        """Причина завершения в GUI-поток; устаревшие прогоны игнорируются."""
        if run_id != self._run_id:
            logger.debug("События устаревшего прогона %s отброшены", run_id)
            return
        self.finished.emit(reason.value, detail)
