"""Исполнение плоского списка команд в отдельном потоке (M1–M2)."""

import logging
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import Enum

from core.input.backend import Button, FailsafeTriggered, InputBackend

logger = logging.getLogger(__name__)


class CommandType(Enum):
    """Вид команды сценария."""

    CLICK = "click"
    PAUSE = "pause"
    MOVE = "move"


class StopReason(Enum):
    """Почему исполнитель закончил работу."""

    COMPLETED = "completed"  # пройдены все повторы
    STOPPED = "stopped"  # вызван stop() (кнопка или хоткей)
    FAILSAFE = "failsafe"  # сработала аварийная защита бэкенда
    ERROR = "error"  # любое другое исключение


@dataclass(frozen=True)
class Command:
    """Одна команда сценария."""

    kind: CommandType
    x: int | None = None
    y: int | None = None
    button: Button = Button.LEFT
    duration: float = 0.0  # для move
    seconds: float = 0.0  # для pause


class Executor:
    """Исполняет список команд в daemon-потоке, потокобезопасный стоп."""

    def __init__(
        self,
        backend: InputBackend,
        commands: Sequence[Command],
        interval: float = 0.0,
        repeats: int | None = None,
        on_step: Callable[[int], None] | None = None,
        on_finish: Callable[[StopReason, str], None] | None = None,
    ) -> None:
        """Создать исполнитель.

        Args:
            backend: бэкенд эмуляции ввода.
            commands: плоский список команд.
            interval: пауза между командами, секунды.
            repeats: число проходов по списку; `None` — до остановки.
            on_step: callback после каждой команды (общий счётчик с 1);
                вызывается в потоке исполнителя — только лёгкая работа.
            on_finish: callback по завершении работы: причина и подробности
                (пустая строка или текст ошибки); вызывается один раз
                в потоке исполнителя.
        """
        if interval < 0:
            raise ValueError("interval не может быть отрицательным")
        if repeats is not None and repeats < 0:
            raise ValueError("repeats не может быть отрицательным")

        self._backend = backend
        self._commands = tuple(commands)
        self._interval = interval
        self._repeats = repeats
        self._on_step = on_step
        self._on_finish = on_finish

        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._steps = 0

    @property
    def is_running(self) -> bool:
        """Идёт ли исполнение прямо сейчас."""
        thread = self._thread
        return thread is not None and thread.is_alive() and not self._stop.is_set()

    def start(self) -> None:
        """Запустить исполнение; no-op, если исполнитель уже работает."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                if not self._stop.is_set():
                    return
                # Предыдущий прогон остановлен, но поток ещё завершается.
                self._thread.join(timeout=0.5)
                if self._thread.is_alive():
                    return
            self._stop.clear()
            self._steps = 0
            self._thread = threading.Thread(
                target=self._run,
                name="clickit-executor",
                daemon=True,
            )
            self._thread.start()

    def stop(self) -> None:
        """Запросить остановку: исполнитель завершится на ближайшей проверке."""
        self._stop.set()

    def join(self, timeout: float | None = None) -> bool:
        """Дождаться завершения потока. `True` — поток завершился."""
        thread = self._thread
        if thread is None:
            return True
        thread.join(timeout=timeout)
        return not thread.is_alive()

    def _run(self) -> None:
        """Тело потока: проходы по списку команд до стопа или конца повторов."""
        reason = StopReason.COMPLETED
        detail = ""
        try:
            if self._commands and self._repeats != 0:
                passes = 0
                while not self._stop.is_set():
                    if self._repeats is not None and passes >= self._repeats:
                        break
                    if not self._run_pass():
                        break
                    passes += 1
                if self._stop.is_set():
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

    def _run_pass(self) -> bool:
        """Выполнить один проход по списку. `False` — прерван остановкой."""
        for command in self._commands:
            if self._stop.is_set():
                return False
            # Интервал выдерживается перед каждой командой, кроме самой первой:
            # после последней команды пауза не нужна (стоп срабатывает сразу).
            if self._steps > 0 and self._stop.wait(self._interval):
                return False
            self._execute(command)
            self._steps += 1
            if self._on_step is not None:
                self._on_step(self._steps)
        return True

    def _notify_finish(self, reason: StopReason, detail: str) -> None:
        """Вызвать `on_finish`, не позволяя ошибке UI убить поток."""
        if self._on_finish is None:
            return
        try:
            self._on_finish(reason, detail)
        except Exception:  # noqa: BLE001 — обратный вызов не должен ломать поток
            logger.exception("Ошибка обработчика завершения исполнителя")

    def _execute(self, command: Command) -> None:
        """Выполнить одну команду через бэкенд."""
        if command.kind is CommandType.CLICK:
            if command.x is None or command.y is None:
                raise ValueError("Команда click требует координаты x и y")
            self._backend.click(command.x, command.y, command.button)
        elif command.kind is CommandType.MOVE:
            if command.x is None or command.y is None:
                raise ValueError("Команда move требует координаты x и y")
            self._backend.move_to(command.x, command.y, command.duration)
        elif command.kind is CommandType.PAUSE:
            self._stop.wait(command.seconds)
        else:  # pragma: no cover — защита от новых видов команд
            raise ValueError(f"Неизвестный вид команды: {command.kind!r}")
