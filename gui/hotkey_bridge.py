"""Глобальные хоткеи приложения → Qt-сигналы (pynput работает в своём потоке)."""

from PySide6.QtCore import QObject, Signal

from core.hotkeys import HotkeyManager
from core.settings import Settings


class HotkeyBridge(QObject):
    """Единая точка глобальных хоткеев: F5 — старт, F6 — стоп, F8 — точка.

    Callback'и pynput выполняются в потоке слушателя, поэтому они только
    испускают сигналы: любая работа с виджетами — в GUI-потоке.
    """

    start_requested = Signal()
    stop_requested = Signal()
    pick_requested = Signal()

    def __init__(self, settings: Settings, parent: QObject | None = None) -> None:
        """Зарегистрировать привязки из настроек (до `start()`)."""
        super().__init__(parent)
        self._manager = HotkeyManager()
        self._manager.register(settings.hotkey_start, self.start_requested.emit)
        self._manager.register(settings.hotkey_stop, self.stop_requested.emit)
        self._manager.register(settings.hotkey_pick, self.pick_requested.emit)

    def start(self) -> None:
        """Запустить слушатель глобальных хоткеев (идемпотентно)."""
        self._manager.start()

    def stop(self) -> None:
        """Остановить слушатель (идемпотентно)."""
        self._manager.stop()
