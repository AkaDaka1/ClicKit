"""Смоук-тесты диалога настроек: значения, сброс, проверка конфликтов (offscreen)."""

from PySide6.QtWidgets import QDialog

from core.settings import Settings
from gui.settings_dialog import SettingsDialog


def make_dialog(settings: Settings | None = None) -> SettingsDialog:
    """Диалог с настройками по умолчанию или переданными."""
    return SettingsDialog(settings if settings is not None else Settings())


def test_dialog_shows_saved_values(qt_app: object) -> None:
    """Диалог показывает сохранённую тему и хоткеи в понятном виде."""
    dialog = make_dialog(Settings(theme="light", hotkey_start="<ctrl>+<alt>+s"))

    assert dialog.theme_mode() == "light"
    assert dialog.hotkey_edit("start").spec() == "<ctrl>+<alt>+s"
    assert dialog.hotkey_edit("start").text() == "Ctrl+Alt+S"
    assert dialog.hotkey_edit("stop").text() == "F6"
    assert dialog.hotkey_edit("pick").text() == "F8"

    dialog.deleteLater()


def test_reset_returns_defaults(qt_app: object) -> None:
    """Кнопка сброса возвращает F5/F6/F8."""
    dialog = make_dialog()
    dialog.hotkey_edit("start").set_spec("<ctrl>+<alt>+s")

    dialog.reset_hotkeys()

    assert dialog.hotkeys() == {
        "start": "<f5>",
        "stop": "<f6>",
        "pick": "<f8>",
    }
    dialog.deleteLater()


def test_duplicate_hotkeys_block_accept(qt_app: object) -> None:
    """Одинаковые сочетания не дают закрыть диалог и подсвечивают поля."""
    dialog = make_dialog()
    dialog.hotkey_edit("stop").set_spec("<f5>")

    dialog.accept()

    assert dialog.result() != QDialog.DialogCode.Accepted
    assert dialog.hotkey_edit("start").property("invalid") is True
    assert dialog.hotkey_edit("stop").property("invalid") is True
    dialog.deleteLater()


def test_empty_stop_blocks_accept(qt_app: object) -> None:
    """Аварийный стоп нельзя оставить пустым."""
    dialog = make_dialog()
    dialog.hotkey_edit("stop").set_spec("")

    dialog.accept()

    assert dialog.result() != QDialog.DialogCode.Accepted
    assert dialog.hotkey_edit("stop").property("invalid") is True
    assert dialog.hotkey_edit("start").property("invalid") is False
    dialog.deleteLater()


def test_valid_changes_are_accepted(qt_app: object) -> None:
    """Корректные значения принимаются и доступны вызывающему коду."""
    dialog = make_dialog()
    dialog.set_theme_mode("dark")
    dialog.hotkey_edit("start").set_spec("<ctrl>+<alt>+s")
    dialog.hotkey_edit("pick").set_spec("<ctrl>+<alt>+p")

    dialog.accept()

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.theme_mode() == "dark"
    assert dialog.hotkeys() == {
        "start": "<ctrl>+<alt>+s",
        "stop": "<f6>",
        "pick": "<ctrl>+<alt>+p",
    }
    dialog.deleteLater()


def test_invalid_value_from_capture_is_marked(qt_app: object) -> None:
    """Недопустимое сочетание из виджета помечается ошибкой, но не меняет хоткей."""
    dialog = make_dialog()
    edit = dialog.hotkey_edit("start")

    edit.set_spec("<ctrl>")

    assert edit.spec() == "<ctrl>"
    dialog.accept()
    assert dialog.result() != QDialog.DialogCode.Accepted
    assert edit.property("invalid") is True
    dialog.deleteLater()
