"""Глобальные хоткеи на основе pynput (слушатель в отдельном потоке)."""

import logging
import threading
from collections.abc import Callable, Mapping

from pynput import keyboard

logger = logging.getLogger(__name__)


class HotkeyManager:
    """Регистрация глобальных хоткеев и управление слушателем.

    Регистрация возможна только до `start()`: слушатель строится по
    снимку привязок. Callback'и выполняются в потоке слушателя — только
    установка флагов/событий, никакой тяжёлой работы.
    """

    def __init__(self) -> None:
        self._bindings: dict[str, Callable[[], None]] = {}
        self._listener: keyboard.GlobalHotKeys | None = None
        self._lock = threading.RLock()

    def register(self, spec: str, callback: Callable[[], None]) -> None:
        """Привязать хоткей в формате pynput (`'<f6>'`, `'<ctrl>+<alt>+s'`)."""
        with self._lock:
            if self._listener is not None:
                raise RuntimeError(
                    "Нельзя регистрировать хоткеи после запуска слушателя"
                )
            self._bindings[spec] = callback

    def start(self) -> None:
        """Запустить слушатель (идемпотентно)."""
        with self._lock:
            if self._listener is not None or not self._bindings:
                return
            self._listener = keyboard.GlobalHotKeys(
                {
                    spec: self._wrap(spec, callback)
                    for spec, callback in self._bindings.items()
                }
            )
            self._listener.start()

    def stop(self) -> None:
        """Остановить слушатель (идемпотентно)."""
        with self._lock:
            if self._listener is None:
                return
            self._listener.stop()
            self._listener = None

    def reload(self, bindings: Mapping[str, Callable[[], None]]) -> None:
        """Заменить привязки и перезапустить слушатель, если он работал.

        Нужен для смены хоткеев из настроек без перезапуска приложения.
        """
        with self._lock:
            was_running = self._listener is not None
            self.stop()
            self._bindings = dict(bindings)
            if was_running:
                self.start()

    @staticmethod
    def _wrap(spec: str, callback: Callable[[], None]) -> Callable[[], None]:
        """Обернуть callback, чтобы исключение не убивало слушатель."""

        def handler() -> None:
            try:
                callback()
            except Exception:  # noqa: BLE001 — слушатель должен жить дальше
                logger.exception("Ошибка обработчика хоткея %s", spec)

        return handler
