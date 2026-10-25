"""Смоук-тесты GUI: окно собирается, форма переключает состояние (offscreen)."""

import time
from collections.abc import Callable
from pathlib import Path

from PySide6.QtWidgets import QApplication, QPushButton, QSpinBox, QTabWidget, QWidget

from core.input.backend import Button
from core.settings import Settings, SettingsStore
from gui.main_window import MainWindow
from gui.simple_mode.view import START_TEXT, STOP_TEXT
from tests.test_executor import MockBackend


def wait_gui(predicate: Callable[[], bool], timeout: float = 2.0) -> bool:
    """Ждать условия, прокачивая очередь событий Qt (цикл событий не запущен)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        QApplication.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    QApplication.processEvents()
    return predicate()


def find_start_button(window: QWidget) -> QPushButton:
    """Кнопка старта/стопа — единственная с такими подписями."""
    for button in window.findChildren(QPushButton):
        if button.text() in (START_TEXT, STOP_TEXT):
            return button
    raise AssertionError("Кнопка старта не найдена")


def find_button(window: QWidget, text: str) -> QPushButton:
    """Найти кнопку по подписи."""
    for button in window.findChildren(QPushButton):
        if button.text() == text:
            return button
    raise AssertionError(f"Кнопка «{text}» не найдена")


def make_window(
    tmp_path: Path, backend: MockBackend, **overrides: object
) -> MainWindow:
    """Окно с mock-бэкендом и временным файлом настроек (без глобальных хоткеев)."""
    values: dict[str, object] = {
        "x": 5,
        "y": 6,
        "interval_ms": 1,
        "repeats": 1,
        "close_action_idle": "quit",
    }
    values.update(overrides)
    store = SettingsStore(tmp_path / "settings.json")
    return MainWindow(
        settings=Settings(**values),  # type: ignore[arg-type]
        store=store,
        backend=backend,
        enable_hotkeys=False,
    )


def test_main_window_has_two_tabs(qt_app: object, tmp_path: Path) -> None:
    """В главном окне две вкладки: простой режим и редактор."""
    window = make_window(tmp_path, MockBackend())

    tabs = window.findChild(QTabWidget)
    assert tabs is not None
    assert tabs.count() == 2
    assert tabs.tabText(0) == "Простой режим"
    assert tabs.tabText(1) == "Редактор сценариев"
    assert find_start_button(window).text() == START_TEXT

    window.hide()
    window.deleteLater()


def test_start_click_and_auto_finish(qt_app: object, tmp_path: Path) -> None:
    """Клик по «Старт» выполняет ровно один клик и возвращает форму в «готов»."""
    backend = MockBackend()
    window = make_window(tmp_path, backend)
    button = find_start_button(window)

    button.click()
    assert button.text() == STOP_TEXT

    assert wait_gui(lambda: len(backend.calls) == 1)
    assert backend.calls[0] == ("click", (5, 6, Button.LEFT))
    assert wait_gui(lambda: button.text() == START_TEXT)

    window.hide()
    window.deleteLater()


def test_capture_point_fills_coordinates(qt_app: object, tmp_path: Path) -> None:
    """Кнопка захвата точки берёт позицию курсора у бэкенда."""
    window = make_window(tmp_path, MockBackend(), x=0, y=0)
    spins = window.findChildren(QSpinBox)
    assert spins, "На форме нет полей координат"

    find_button(window, "Захватить точку (F8)").click()

    expected = MockBackend().position()
    assert (spins[0].value(), spins[1].value()) == expected

    window.hide()
    window.deleteLater()
