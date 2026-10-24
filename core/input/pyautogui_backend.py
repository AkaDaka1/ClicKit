"""Бэкенд эмуляции ввода на pyautogui (ADR №7 — единственный «отправляющий»)."""

import pyautogui

from core.input.backend import Button, InputBackend

# Курсор в углу экрана — аварийный стоп (работает и без GUI).
pyautogui.FAILSAFE = True
# Встроенные паузы pyautogui не должны искажать интервал сценария.
pyautogui.PAUSE = 0


class PyAutoguiBackend(InputBackend):
    """Реализация `InputBackend` поверх pyautogui (Win32 SendInput)."""

    def click(self, x: int, y: int, button: Button = Button.LEFT) -> None:
        """Одиночный клик в абсолютных координатах экрана."""
        pyautogui.click(x=x, y=y, button=button.value)

    def double_click(self, x: int, y: int, button: Button = Button.LEFT) -> None:
        """Двойной клик в абсолютных координатах экрана."""
        pyautogui.doubleClick(x=x, y=y, button=button.value)

    def move_to(self, x: int, y: int, duration: float = 0.0) -> None:
        """Переместить курсор в точку. `duration` — секунды, 0 — мгновенно."""
        pyautogui.moveTo(x, y, duration=duration)

    def drag_to(
        self,
        x: int,
        y: int,
        duration: float = 0.5,
        button: Button = Button.LEFT,
    ) -> None:
        """Перетащить курсор в точку, удерживая `button`."""
        pyautogui.dragTo(x, y, duration=duration, button=button.value)

    def press_key(self, keys: str) -> None:
        """Нажать комбинацию клавиш: 'ctrl+s' — hotkey, 'f1' — одиночное нажатие."""
        parts = [part.strip().lower() for part in keys.split("+") if part.strip()]
        if not parts:
            raise ValueError("Пустая комбинация клавиш")
        if len(parts) == 1:
            pyautogui.press(parts[0])
        else:
            pyautogui.hotkey(*parts)

    def scroll(
        self,
        amount: int,
        x: int | None = None,
        y: int | None = None,
    ) -> None:
        """Колесо мыши: `amount > 0` — вверх, `amount < 0` — вниз."""
        pyautogui.scroll(amount, x=x, y=y)
