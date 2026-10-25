"""Сборка QApplication и главного окна."""

import logging
import sys

from PySide6.QtWidgets import QApplication

from app.paths import resource_path
from core.settings import SettingsStore
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


def run() -> int:
    """Точка входа: создать приложение, окно, запустить цикл событий."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    app = QApplication(sys.argv)
    app.setApplicationName("ClicKit")
    app.setApplicationDisplayName("ClicKit")
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName("ClicKit")
    app.setWindowIcon(app_icon())
    # Окно может быть спрятано в трей — приложение живёт без видимых окон.
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet(load_stylesheet())

    store = SettingsStore()
    window = MainWindow(settings=store.load(), store=store)
    window.show()
    return app.exec()
