"""Сборка QApplication и главного окна."""

import logging
import sys

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication

from app.logging_setup import install_excepthook, setup_logging
from app.version import APP_VERSION
from core.settings import Settings, SettingsStore
from gui.icons import app_icon
from gui.main_window import MainWindow
from gui.theme import ThemeManager

logger = logging.getLogger(__name__)

__all__ = ["APP_VERSION", "initial_settings", "run"]


def initial_settings(store: SettingsStore, center: tuple[int, int] | None) -> Settings:
    """Настройки при запуске: при первом запуске точка — центр экрана.

    Координаты `(0, 0)` — аварийный угол pyautogui, там клики сразу
    останавливаются, поэтому в качестве стартовой точки берётся центр.
    """
    settings = store.load()
    if not store.path.exists() and center is not None:
        settings.x, settings.y = center
    return settings


def run() -> int:
    """Точка входа: журнал, приложение, окно, цикл событий."""
    journal = setup_logging()
    install_excepthook()
    logger.info("ClicKit %s запускается; журнал: %s", APP_VERSION, journal)

    app = QApplication(sys.argv)
    app.setApplicationName("ClicKit")
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName("ClicKit")
    app.setWindowIcon(app_icon())
    # Окно может быть спрятано в трей — приложение живёт без видимых окон.
    app.setQuitOnLastWindowClosed(False)

    store = SettingsStore()
    settings = initial_settings(store, _screen_center(app))
    theme = ThemeManager(settings.theme)
    theme.apply(app)

    window = MainWindow(settings=settings, store=store, theme=theme)
    window.show()
    code = app.exec()
    # QtWebEngine на Windows падает, если webview переживает QApplication:
    # уничтожаем окно и отложенные объекты до выхода из процесса.
    window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()
    return code


def _screen_center(app: QApplication) -> tuple[int, int] | None:
    """Центр доступной области основного экрана (для первого запуска)."""
    screen = app.primaryScreen()
    if screen is None:
        return None
    point = screen.availableGeometry().center()
    return (point.x(), point.y())
