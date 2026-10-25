"""Общая настройка тестов: Qt работает без экрана."""

import os

# Offscreen-платформа нужна, чтобы смоук-тесты GUI не открывали окна.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402 — переменная окружения должна быть установлена раньше Qt


@pytest.fixture(scope="session")
def qt_app() -> object:
    """Единственный QApplication на всю сессию тестов."""
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app
