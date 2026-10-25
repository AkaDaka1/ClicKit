"""Пикер координат: F8 фиксирует текущую позицию курсора."""

from PySide6.QtCore import QObject, Signal

from core.input.backend import InputBackend


class CoordinatePicker(QObject):
    """Читает позицию курсора у бэкенда и отдаёт её в GUI-поток.

    Пикер не блокирует окно: пользователь уводит курсор в нужную точку
    и нажимает F8 (глобальный хоткей), после чего координаты попадают в форму.
    """

    captured = Signal(int, int)  # x, y
    failed = Signal(str)

    def __init__(self, backend: InputBackend, parent: QObject | None = None) -> None:
        """Создать пикер поверх бэкенда ввода."""
        super().__init__(parent)
        self._backend = backend

    def capture(self) -> bool:
        """Снять позицию курсора. `False` — считать не удалось."""
        try:
            x, y = self._backend.position()
        except Exception as exc:  # noqa: BLE001 — сбой бэкенда не должен ронять GUI
            self.failed.emit(str(exc) or type(exc).__name__)
            return False
        self.captured.emit(x, y)
        return True
