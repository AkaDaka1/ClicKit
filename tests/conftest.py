"""Общая настройка тестов: Qt работает без экрана."""

import os

# Offscreen-платформа нужна, чтобы смоук-тесты GUI не открывали окна.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# WebEngine в offscreen-режиме: без sandbox и без GPU (только для тестов).
os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu")

import pytest  # noqa: E402 — переменная окружения должна быть установлена раньше Qt

# Код pytest, с которым нужно аварийно завершить процесс (см. ниже).
_webengine_exitstatus: int | None = None


def _qt_webengine_loaded() -> bool:
    """Загружался ли QtWebEngine в этой сессии тестов."""
    import sys

    return "PySide6.QtWebEngineCore" in sys.modules


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Запомнить код выхода и освободить Qt, если работал QtWebEngine.

    PySide6 + xvfb: при разрушении QWebEnginePage остаются живые потоки
    Chromium, и Python падает на финализации («Fatal Python error:
    bool_dealloc»), хотя все тесты прошли. Поэтому после сессии закрываем
    окна и собираем мусор, а сам выход откладываем до `pytest_unconfigure`
    (там JUnit-отчёт и сводка уже записаны). На Windows (целевая
    платформа) поведение не меняется.
    """
    global _webengine_exitstatus
    import sys

    if not sys.platform.startswith("linux") or not _qt_webengine_loaded():
        return
    try:
        from PySide6.QtCore import QCoreApplication, QEvent
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is not None:
            app.closeAllWindows()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            app.processEvents()
        import gc

        gc.collect()
    except Exception:
        pass
    _webengine_exitstatus = int(exitstatus)


def pytest_unconfigure(config: pytest.Config) -> None:
    """Выйти из процесса, минуя финализацию интерпретатора с QtWebEngine."""
    if _webengine_exitstatus is not None:
        os._exit(_webengine_exitstatus)


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
