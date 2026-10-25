"""Иконка в системном трее: управление кликами при скрытом окне."""

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon, QWidget


class TrayIcon(QObject):
    """Иконка трея с меню: показать окно, старт, стоп, выход.

    Сигналы повторяют действия меню, чтобы главное окно оставалось
    единственным местом, где меняется состояние приложения.
    """

    show_requested = Signal()
    start_requested = Signal()
    stop_requested = Signal()
    quit_requested = Signal()

    def __init__(self, icon: QIcon, window: QWidget) -> None:
        """Создать иконку трея, привязанную к главному окну."""
        super().__init__(window)
        self._tray = QSystemTrayIcon(icon, window)
        self._tray.setToolTip("ClicKit — автокликер")

        menu = QMenu(window)
        self._show_action = menu.addAction("Показать ClicKit")
        self._start_action = menu.addAction("Старт (F5)")
        self._stop_action = menu.addAction("Стоп (F6)")
        menu.addSeparator()
        self._quit_action = menu.addAction("Выход")
        self._menu = menu

        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_activated)

        self._show_action.triggered.connect(lambda: self.show_requested.emit())
        self._start_action.triggered.connect(lambda: self.start_requested.emit())
        self._stop_action.triggered.connect(lambda: self.stop_requested.emit())
        self._quit_action.triggered.connect(lambda: self.quit_requested.emit())

    @staticmethod
    def is_available() -> bool:
        """Есть ли в системе системный трей."""
        return QSystemTrayIcon.isSystemTrayAvailable()

    def show(self) -> None:
        """Показать иконку в трее."""
        self._tray.show()

    def hide(self) -> None:
        """Убрать иконку из трея (при выходе)."""
        self._tray.hide()

    def set_running(self, running: bool) -> None:
        """Включить/выключить пункты меню в зависимости от состояния кликов."""
        self._start_action.setEnabled(not running)
        self._stop_action.setEnabled(running)
        self._tray.setToolTip(
            "ClicKit — клики выполняются" if running else "ClicKit — автокликер"
        )

    def notify(self, title: str, text: str) -> None:
        """Показать всплывающее уведомление, если система их поддерживает."""
        if not QSystemTrayIcon.supportsMessages():
            return
        self._tray.showMessage(
            title, text, QSystemTrayIcon.MessageIcon.Information, 4000
        )

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        """Клик по иконке возвращает окно (одиночный или двойной)."""
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.show_requested.emit()
