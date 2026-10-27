"""Общая настройка тестов: Qt работает без экрана."""

import os

# Offscreen-платформа нужна, чтобы смоук-тесты GUI не открывали окна.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# WebEngine в offscreen-режиме: без sandbox и без GPU (только для тестов).
os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu")

import pytest  # noqa: E402 — переменная окружения должна быть установлена раньше Qt


@pytest.fixture(scope="session")
def qt_app() -> object:
    """Единственный QApplication на всю сессию тестов.

    Перед завершением процесса принудительно уничтожаем отложенные виджеты:
    QtWebEngine на Windows падает, если webview переживает QApplication.
    """
    from PySide6.QtCore import QCoreApplication, QEvent
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app
    app.closeAllWindows()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()
