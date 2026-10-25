"""Параметры запуска «Простого режима» (без зависимости от Qt)."""

from dataclasses import dataclass

from core.executor import Command, CommandType
from core.input.backend import Button
from core.settings import MAX_INTERVAL_MS, MAX_REPEATS, MIN_INTERVAL_MS, MIN_REPEATS


@dataclass(frozen=True)
class SimpleRunConfig:
    """Параметры одного запуска автокликера в точку."""

    x: int
    y: int
    button: Button = Button.LEFT
    interval_ms: int = 100
    repeats: int | None = 100  # None — кликать до остановки

    def __post_init__(self) -> None:
        """Проверить диапазоны интервала и числа повторов."""
        if not MIN_INTERVAL_MS <= self.interval_ms <= MAX_INTERVAL_MS:
            raise ValueError(
                f"Интервал должен быть от {MIN_INTERVAL_MS} до {MAX_INTERVAL_MS} мс"
            )
        if self.repeats is not None and not MIN_REPEATS <= self.repeats <= MAX_REPEATS:
            raise ValueError(
                f"Число повторов должно быть от {MIN_REPEATS} до {MAX_REPEATS}"
            )

    @property
    def interval_seconds(self) -> float:
        """Интервал в секундах — в таком виде его ждёт `Executor`."""
        return self.interval_ms / 1000.0

    def commands(self) -> list[Command]:
        """Команды для исполнителя: одиночный клик в заданную точку."""
        return [Command(CommandType.CLICK, x=self.x, y=self.y, button=self.button)]
