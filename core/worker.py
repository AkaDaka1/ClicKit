"""Общий потоковый воркер: запуск, остановка и причина завершения."""

import logging
import threading
from abc import ABC, abstractmethod
from collections.abc import Callable
from enum import Enum

from core.input.backend import FailsafeTriggered

logger = logging.getLogger(__name__)


class StopReason(Enum):
    """Почему воркер закончил работу."""

    COMPLETED = "completed"  # работа пройдена до конца
    STOPPED = "stopped"  # вызван stop() (кнопка или хоткей)
    FAILSAFE = "failsafe"  # сработала аварийная защита бэкенда
    ERROR = "error"  # любое другое исключение


class ThreadedWorker(ABC):
    """Выполняет работу в daemon-потоке с потокобезопасным стопом.

    Потомки реализуют только `_run_body()`; запуск, ожидание, обработка
    аварийной защиты и уведомление о завершении — здесь, в одном месте.
    """

    #: Имя потока (удобно для отладки и логов).
    thread_name = "clickit-worker"

    def __init__(
        self,
        on_finish: Callable[[StopReason, str], None] | None = None,
    ) -> None:
        """Создать воркер.

        Args:
            on_finish: callback по завершении работы: причина и подробности
                (пустая строка или текст ошибки); вызывается один раз
                в потоке воркера.
        """
        self._on_finish = on_finish
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None

    @property
    def is_running(self) -> bool:
        """Идёт ли исполнение прямо сейчас."""
        thread = self._thread
        return thread is not None and thread.is_alive() and not self._stop.is_set()

    def start(self) -> None:
        """Запустить работу; no-op, если воркер уже работает."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                if not self._stop.is_set():
                    return
                # Предыдущий прогон остановлен, но поток ещё завершается.
                self._thread.join(timeout=0.5)
                if self._thread.is_alive():
                    return
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._run,
                name=self.thread_name,
                daemon=True,
            )
            self._thread.start()

    def stop(self) -> None:
        """Запросить остановку: воркер завершится на ближайшей проверке."""
        self._stop.set()

    def join(self, timeout: float | None = None) -> bool:
        """Дождаться завершения потока. `True` — поток завершился."""
        thread = self._thread
        if thread is None:
            return True
        thread.join(timeout=timeout)
        return not thread.is_alive()

    @abstractmethod
    def _run_body(self, stop: threading.Event) -> bool:
        """Выполнить работу.

        Args:
            stop: флаг остановки — проверять перед каждым шагом и ждать
                паузы через `stop.wait(...)`, чтобы стоп срабатывал сразу.

        Returns:
            `True` — работа пройдена до конца, `False` — прервана стопом.
        """

    def _run(self) -> None:
        """Тело потока: работа, определение причины и `on_finish`."""
        reason = StopReason.COMPLETED
        detail = ""
        try:
            if not self._run_body(self._stop) or self._stop.is_set():
                reason = StopReason.STOPPED
        except FailsafeTriggered as exc:
            reason = StopReason.FAILSAFE
            detail = str(exc)
            logger.info("Сработала аварийная защита (курсор в углу экрана)")
        except Exception as exc:  # noqa: BLE001 — поток не должен падать молча
            reason = StopReason.ERROR
            detail = str(exc) or type(exc).__name__
            logger.exception("Ошибка исполнения сценария")
        finally:
            self._stop.set()
            self._notify_finish(reason, detail)

    def _notify_finish(self, reason: StopReason, detail: str) -> None:
        """Вызвать `on_finish`, не позволяя ошибке UI убить поток."""
        if self._on_finish is None:
            return
        try:
            self._on_finish(reason, detail)
        except Exception:  # noqa: BLE001 — обратный вызов не должен ломать поток
            logger.exception("Ошибка обработчика завершения воркера")
