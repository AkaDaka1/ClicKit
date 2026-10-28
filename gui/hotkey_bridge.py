"""Глобальные хоткеи приложения → Qt-сигналы (pynput работает в своём потоке)."""

from collections.abc import Callable

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
        self._register(settings)

    def _register(self, settings: Settings) -> None:
        """Привязать три действия к спецификациям из настроек."""
        for spec, callback in self._bindings(settings).items():
            self._manager.register(spec, callback)

    def _bindings(self, settings: Settings) -> dict[str, Callable[[], None]]:
        """Спецификации хоткеев → callbacks (только испускание сигналов)."""
        return {
            settings.hotkey_start: self.start_requested.emit,
            settings.hotkey_stop: self.stop_requested.emit,
            settings.hotkey_pick: self.pick_requested.emit,
        }

    def reload(self, settings: Settings) -> None:
        """Применить новые хоткеи без перезапуска приложения."""
        self._manager.reload(self._bindings(settings))

    def start(self) -> None:
        """Запустить слушатель глобальных хоткеев (идемпотентно)."""
        self._manager.start()

    def stop(self) -> None:
        """Остановить слушатель (идемпотентно)."""
        self._manager.stop()
