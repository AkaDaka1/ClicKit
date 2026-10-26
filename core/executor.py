"""Исполнение плоского списка команд в отдельном потоке (M1–M2)."""

import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import Enum

from core.input.backend import Button, InputBackend
from core.worker import StopReason, ThreadedWorker

__all__ = ["Command", "CommandType", "Executor", "StopReason"]


class CommandType(Enum):
    """Вид команды сценария."""

    CLICK = "click"
    PAUSE = "pause"
    MOVE = "move"


@dataclass(frozen=True)
class Command:
    """Одна команда сценария."""

    kind: CommandType
    x: int | None = None
    y: int | None = None
    button: Button = Button.LEFT
    duration: float = 0.0  # для move
    seconds: float = 0.0  # для pause


class Executor(ThreadedWorker):
    """Исполняет список команд в daemon-потоке, потокобезопасный стоп."""

    thread_name = "clickit-executor"

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

        super().__init__(on_finish=on_finish)
        self._backend = backend
        self._commands = tuple(commands)
        self._interval = interval
        self._repeats = repeats
        self._on_step = on_step
        self._steps = 0

    def _run_body(self, stop: threading.Event) -> bool:
        """Проходы по списку команд до стопа или конца повторов."""
        self._steps = 0
        if not self._commands or self._repeats == 0:
            return True
        passes = 0
        while not stop.is_set():
            if self._repeats is not None and passes >= self._repeats:
                break
            if not self._run_pass(stop):
                return False
            passes += 1
        return not stop.is_set()

    def _run_pass(self, stop: threading.Event) -> bool:
        """Выполнить один проход по списку. `False` — прерван остановкой."""
        for command in self._commands:
            if stop.is_set():
                return False
            # Интервал выдерживается перед каждой командой, кроме самой первой:
            # после последней команды пауза не нужна (стоп срабатывает сразу).
            if self._steps > 0 and stop.wait(self._interval):
                return False
            self._execute(command, stop)
            self._steps += 1
            if self._on_step is not None:
                self._on_step(self._steps)
        return True

    def _execute(self, command: Command, stop: threading.Event) -> None:
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
            stop.wait(command.seconds)
        else:  # pragma: no cover — защита от новых видов команд
            raise ValueError(f"Неизвестный вид команды: {command.kind!r}")
