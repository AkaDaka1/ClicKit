"""Бэкенд эмуляции ввода на pyautogui (ADR №7 — единственный «отправляющий»)."""

import functools
from collections.abc import Callable
from typing import ParamSpec

import pyautogui

from core.input.backend import Button, FailsafeTriggered, InputBackend

# Курсор в углу экрана — аварийный стоп (работает и без GUI).
pyautogui.FAILSAFE = True
# Встроенные паузы pyautogui не должны искажать интервал сценария.
pyautogui.PAUSE = 0

_P = ParamSpec("_P")


def _translate_failsafe(func: Callable[_P, None]) -> Callable[_P, None]:
    """Преобразовать `pyautogui.FailSafeException` в `FailsafeTriggered`.

    Движок (`core/`) не должен зависеть от pyautogui, поэтому наружу
    отдаётся собственное исключение с понятным статусом для GUI.
    """

    @functools.wraps(func)
    def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> None:
        try:
            func(*args, **kwargs)
        except pyautogui.FailSafeException as exc:
            raise FailsafeTriggered(str(exc)) from exc

    return wrapper


class PyAutoguiBackend(InputBackend):
    """Реализация `InputBackend` поверх pyautogui (Win32 SendInput)."""

    def position(self) -> tuple[int, int]:
        """Текущая позиция курсора в абсолютных координатах экрана."""
        point = pyautogui.position()
        return int(point.x), int(point.y)

    @_translate_failsafe
    def click(self, x: int, y: int, button: Button = Button.LEFT) -> None:
        """Одиночный клик в абсолютных координатах экрана."""
        pyautogui.click(x=x, y=y, button=button.value)

    @_translate_failsafe
    def double_click(self, x: int, y: int, button: Button = Button.LEFT) -> None:
        """Двойной клик в абсолютных координатах экрана."""
        pyautogui.doubleClick(x=x, y=y, button=button.value)

    @_translate_failsafe
    def move_to(self, x: int, y: int, duration: float = 0.0) -> None:
        """Переместить курсор в точку. `duration` — секунды, 0 — мгновенно."""
        pyautogui.moveTo(x, y, duration=duration)

    @_translate_failsafe
    def drag_to(
        self,
        x: int,
        y: int,
        duration: float = 0.5,
        button: Button = Button.LEFT,
    ) -> None:
        """Перетащить курсор в точку, удерживая `button`."""
        pyautogui.dragTo(x, y, duration=duration, button=button.value)

    @_translate_failsafe
    def press_key(self, keys: str) -> None:
        """Нажать комбинацию клавиш: 'ctrl+s' — hotkey, 'f1' — одиночное нажатие."""
        parts = [part.strip().lower() for part in keys.split("+") if part.strip()]
        if not parts:
            raise ValueError("Пустая комбинация клавиш")
        if len(parts) == 1:
            pyautogui.press(parts[0])
        else:
            pyautogui.hotkey(*parts)

    @_translate_failsafe
    def scroll(
        self,
        amount: int,
        x: int | None = None,
        y: int | None = None,
    ) -> None:
        """Колесо мыши: `amount > 0` — вверх, `amount < 0` — вниз."""
        pyautogui.scroll(amount, x=x, y=y)
