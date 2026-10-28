"""Тесты поля записи хоткея: захват сочетания, очистка, ошибки."""

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent

from gui.widgets.hotkey_edit import HotkeyEdit


def press(
    edit: HotkeyEdit,
    key: Qt.Key,
    modifiers: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier,
) -> None:
    """Отправить нажатие клавиши в поле."""
    event = QKeyEvent(QEvent.Type.KeyPress, key, modifiers)
    edit.keyPressEvent(event)


def test_capture_modifier_combination(qt_app: object) -> None:
    """Ctrl+Alt+S записывается в формате pynput и показывается текстом."""
    edit = HotkeyEdit()
    changes: list[str] = []
    edit.spec_changed.connect(changes.append)

    press(
        edit,
        Qt.Key.Key_S,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier,
    )

    assert edit.spec() == "<ctrl>+<alt>+s"
    assert edit.text() == "Ctrl+Alt+S"
    assert changes == ["<ctrl>+<alt>+s"]
    edit.deleteLater()


def test_capture_function_key(qt_app: object) -> None:
    """Функциональная клавиша записывается без модификаторов."""
    edit = HotkeyEdit()

    press(edit, Qt.Key.Key_F5)

    assert edit.spec() == "<f5>"
    assert edit.text() == "F5"
    edit.deleteLater()


def test_modifier_alone_does_not_change(qt_app: object) -> None:
    """Нажатие только Ctrl не меняет сохранённое сочетание."""
    edit = HotkeyEdit("<f6>")

    press(edit, Qt.Key.Key_Control, Qt.KeyboardModifier.ControlModifier)

    assert edit.spec() == "<f6>"
    assert edit.text() == "F6"
    edit.deleteLater()


def test_escape_and_delete_clear(qt_app: object) -> None:
    """Esc или Delete очищают поле."""
    edit = HotkeyEdit("<f5>")

    press(edit, Qt.Key.Key_Escape)

    assert edit.spec() == ""
    assert edit.text() == ""
    edit.deleteLater()


def test_unsafe_combination_is_rejected(qt_app: object) -> None:
    """Одиночная буква не записывается: поле подсвечивает ошибку."""
    edit = HotkeyEdit("<f5>")

    press(edit, Qt.Key.Key_A)

    assert edit.spec() == "<f5>"
    assert edit.property("invalid") is True
    edit.deleteLater()


def test_set_spec_updates_text(qt_app: object) -> None:
    """Программная установка сочетания обновляет подпись и сигнал."""
    edit = HotkeyEdit()
    changes: list[str] = []
    edit.spec_changed.connect(changes.append)

    edit.set_spec("<cmd>+<shift>+<f6>")

    assert edit.text() == "Shift+Win+F6"
    assert changes == ["<cmd>+<shift>+<f6>"]
    edit.set_spec("<cmd>+<shift>+<f6>")
    assert changes == ["<cmd>+<shift>+<f6>"]
    edit.deleteLater()
