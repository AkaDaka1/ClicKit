"""Тесты закрытия окна: два диалога, «Запомнить выбор», остановка кликов.

Диалог открывается модально, поэтому кнопку нажимает таймер, а не тест.
Трей подменяется на «доступный»: offscreen-платформа не имеет трея.
"""

from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QMessageBox,
    QPushButton,
    QWidget,
)

from core.input.backend import Button
from core.settings import Settings, SettingsStore
from gui.main_window import CLOSE_QUIT, CLOSE_TRAY, MainWindow
from gui.simple_mode.view import START_TEXT, STOP_TEXT
from gui.tray import TrayIcon
from tests.test_executor import MockBackend
from tests.test_gui_smoke import wait_gui


def find_button(window: QWidget, text: str) -> QPushButton:
    """Найти кнопку по подписи."""
    for button in window.findChildren(QPushButton):
        if button.text() == text:
            return button
    raise AssertionError(f"Кнопка «{text}» не найдена")


def reject_any_modal() -> None:
    """Страховка от зависания: закрыть оставшийся модальный диалог."""
    box = QApplication.activeModalWidget()
    if isinstance(box, QMessageBox):
        box.reject()


def answer_dialog(button_text: str, remember: bool, problems: list[str]) -> None:
    """Нажать кнопку в открытом модальном диалоге (вызывается таймером)."""
    box = QApplication.activeModalWidget()
    if not isinstance(box, QMessageBox):
        problems.append("модальный диалог не появился")
        QTimer.singleShot(500, reject_any_modal)
        return

    checkbox = box.findChild(QCheckBox)
    if checkbox is not None:
        checkbox.setChecked(remember)

    for button in box.findChildren(QPushButton):
        if button.text() == button_text:
            button.click()
            return

    problems.append(f"в диалоге нет кнопки «{button_text}»")
    box.reject()


def make_window(
    tmp_path: Path,
    settings: Settings,
    backend: MockBackend | None = None,
) -> tuple[MainWindow, SettingsStore]:
    """Показанное окно с треем «как в системе» и временным файлом настроек."""
    store = SettingsStore(tmp_path / "settings.json")
    window = MainWindow(
        settings=settings,
        store=store,
        backend=backend if backend is not None else MockBackend(),
        enable_hotkeys=False,
    )
    window.show()
    return window, store


def test_close_idle_remembers_tray(qt_app: object, tmp_path: Path, monkeypatch) -> None:
    """Без активных кликов диалог предлагает трей, выбор запоминается."""
    monkeypatch.setattr(TrayIcon, "is_available", staticmethod(lambda: True))
    window, store = make_window(
        tmp_path,
        Settings(close_action_idle="ask", close_action_running="ask"),
    )
    problems: list[str] = []

    QTimer.singleShot(200, lambda: answer_dialog("Свернуть в трей", True, problems))
    window.close()

    assert problems == []
    assert store.load().close_action_idle == CLOSE_TRAY
    # Поведение для «клики идут» не изменилось — настройки независимы.
    assert store.load().close_action_running == "ask"
    assert not window.isVisible()

    window.hide()
    window.deleteLater()


def test_close_running_stops_and_quits(
    qt_app: object, tmp_path: Path, monkeypatch
) -> None:
    """При идущих кликах диалог предлагает остановить их и выйти."""
    monkeypatch.setattr(TrayIcon, "is_available", staticmethod(lambda: True))
    backend = MockBackend()
    window, store = make_window(
        tmp_path,
        Settings(
            x=3,
            y=4,
            interval_ms=3_600_000,  # один клик и долгое ожидание
            repeats=None,
            infinite=True,
            close_action_idle="ask",
            close_action_running="ask",
        ),
        backend,
    )

    start_button = find_button(window, START_TEXT)
    start_button.click()
    assert start_button.text() == STOP_TEXT
    assert wait_gui(lambda: len(backend.calls) == 1)
    assert backend.calls[0] == ("click", (3, 4, Button.LEFT))

    problems: list[str] = []
    QTimer.singleShot(200, lambda: answer_dialog("Остановить и выйти", True, problems))
    window.close()

    assert problems == []
    assert store.load().close_action_running == CLOSE_QUIT
    assert store.load().close_action_idle == "ask"

    window.hide()
    window.deleteLater()


def test_close_uses_remembered_action_without_dialog(
    qt_app: object,
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Запомненное действие применяется сразу, без повторного вопроса."""
    monkeypatch.setattr(TrayIcon, "is_available", staticmethod(lambda: True))
    window, _store = make_window(
        tmp_path,
        Settings(close_action_idle=CLOSE_TRAY, close_action_running=CLOSE_QUIT),
    )

    # Если бы диалог открылся, тест завис бы — это и есть проверка.
    window.close()

    assert not window.isVisible()

    window.hide()
    window.deleteLater()
