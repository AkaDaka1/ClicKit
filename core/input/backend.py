"""Бэкенд эмуляции ввода: контракт для движка."""

from abc import ABC, abstractmethod
from enum import Enum


class Button(Enum):
    """Кнопка мыши."""

    LEFT = "left"
    RIGHT = "right"
    MIDDLE = "middle"


class InputBackend(ABC):
    """Абстрактный интерфейс эмуляции ввода (клики, движения, клавиши)."""

    @abstractmethod
    def click(self, x: int, y: int, button: Button = Button.LEFT) -> None:
        """Одиночный клик в абсолютных координатах экрана."""

    @abstractmethod
    def double_click(self, x: int, y: int, button: Button = Button.LEFT) -> None:
        """Двойной клик в абсолютных координатах экрана."""

    @abstractmethod
    def move_to(self, x: int, y: int, duration: float = 0.0) -> None:
        """Переместить курсор в точку. `duration` — секунды, 0 — мгновенно."""

    @abstractmethod
    def drag_to(
        self,
        x: int,
        y: int,
        duration: float = 0.5,
        button: Button = Button.LEFT,
    ) -> None:
        """Перетащить курсор в точку, удерживая `button`."""

    @abstractmethod
    def press_key(self, keys: str) -> None:
        """Нажать комбинацию клавиш, формат pyautogui: 'ctrl+s', 'f1', 'a'."""

    @abstractmethod
    def scroll(
        self,
        amount: int,
        x: int | None = None,
        y: int | None = None,
    ) -> None:
        """Колесо мыши: `amount > 0` — вверх, `amount < 0` — вниз."""


def create_backend() -> InputBackend:
    """Создать бэкенд ввода (M1: всегда pyautogui, выбор по конфигу — с M2)."""
    from core.input.pyautogui_backend import PyAutoguiBackend

    return PyAutoguiBackend()
