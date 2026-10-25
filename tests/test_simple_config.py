"""Тесты параметров запуска «Простого режима» (без GUI)."""

import pytest

from core.executor import CommandType
from core.input.backend import Button
from gui.simple_mode.config import SimpleRunConfig


def test_interval_seconds() -> None:
    """Миллисекунды переводятся в секунды для исполнителя."""
    config = SimpleRunConfig(x=1, y=2, interval_ms=250)
    assert config.interval_seconds == 0.25


def test_commands_contain_single_click() -> None:
    """Сценарий простого режима — один клик в точку нужной кнопкой."""
    config = SimpleRunConfig(x=10, y=20, button=Button.RIGHT)
    commands = config.commands()

    assert len(commands) == 1
    command = commands[0]
    assert command.kind is CommandType.CLICK
    assert command.x == 10
    assert command.y == 20
    assert command.button is Button.RIGHT


def test_infinite_repeats() -> None:
    """`repeats=None` — «Бесконечно»."""
    assert SimpleRunConfig(x=0, y=0, repeats=None).repeats is None


@pytest.mark.parametrize("interval_ms", [0, -5])
def test_invalid_interval_rejected(interval_ms: int) -> None:
    """Нулевой и отрицательный интервал недопустимы."""
    with pytest.raises(ValueError):
        SimpleRunConfig(x=0, y=0, interval_ms=interval_ms)


def test_invalid_repeats_rejected() -> None:
    """Ноль повторов недопустим (для остановки есть кнопка и F6)."""
    with pytest.raises(ValueError):
        SimpleRunConfig(x=0, y=0, repeats=0)
