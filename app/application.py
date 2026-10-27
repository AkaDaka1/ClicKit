"""Сборка QApplication и главного окна."""

import logging
import sys

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication

from app.paths import resource_path
from core.settings import Settings, SettingsStore
from gui.icons import app_icon
from gui.main_window import MainWindow

logger = logging.getLogger(__name__)

#: Версия приложения (отображается в свойствах; релизы — с M5).
APP_VERSION = "0.2.0"


def load_stylesheet() -> str:
    """Прочитать тёмную тему; при ошибке — пустая строка (стиль по умолчанию)."""
    try:
        return resource_path("styles", "dark.qss").read_text(encoding="utf-8")
    except OSError:
        logger.warning("Не удалось загрузить тему оформления", exc_info=True)
        return ""


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
    """Точка входа: создать приложение, окно, запустить цикл событий."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    app = QApplication(sys.argv)
    app.setApplicationName("ClicKit")
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName("ClicKit")
    app.setWindowIcon(app_icon())
    # Окно может быть спрятано в трей — приложение живёт без видимых окон.
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet(load_stylesheet())

    store = SettingsStore()
    screen = app.primaryScreen()
    center: tuple[int, int] | None = None
    if screen is not None:
        point = screen.availableGeometry().center()
        center = (point.x(), point.y())

    window = MainWindow(settings=initial_settings(store, center), store=store)
    window.show()
    code = app.exec()
    # QtWebEngine на Windows падает, если webview переживает QApplication:
    # уничтожаем окно и отложенные объекты до выхода из процесса.
    window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()
    return code
