"""Главное окно ClicKit."""

from PySide6.QtWidgets import QMainWindow


class MainWindow(QMainWindow):
    """Главное окно приложения (M0: минимальное)."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("ClicKit")
        self.resize(1024, 680)
