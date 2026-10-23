"""Сборка QApplication и главного окна."""

import sys

from PySide6.QtWidgets import QApplication

from gui.main_window import MainWindow


def run() -> int:
    """Точка входа: создать приложение, окно, запустить event loop."""
    app = QApplication(sys.argv)
    app.setApplicationName("ClicKit")
    window = MainWindow()
    window.show()
    return app.exec()
