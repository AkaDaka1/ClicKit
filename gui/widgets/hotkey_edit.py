"""Поле ввода глобального хоткея: «нажмите сочетание» с записью клавиш."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeyEvent, QKeySequence
from PySide6.QtWidgets import QLineEdit, QWidget

from core.hotkey_spec import sequence_to_spec, spec_problem, spec_to_text

#: Клавиши-модификаторы: сами по себе не завершают ввод.
_MODIFIER_KEYS = {
    Qt.Key.Key_Control,
    Qt.Key.Key_Shift,
    Qt.Key.Key_Alt,
    Qt.Key.Key_Meta,
    Qt.Key.Key_AltGr,
    Qt.Key.Key_CapsLock,
    Qt.Key.Key_NumLock,
    Qt.Key.Key_ScrollLock,
}


class HotkeyEdit(QLineEdit):
    """Поле, которое записывает нажатое сочетание клавиш.

    Пользователь ставит курсор в поле и нажимает сочетание; текст
    показывается в человекочитаемом виде, а `spec()` возвращает
    спецификацию pynput для настроек.

    Сигналы:
        spec_changed: изменилась спецификация (пустая строка — не задано).
    """

    spec_changed = Signal(str)

    def __init__(self, spec: str = "", parent: QWidget | None = None) -> None:
        """Создать поле с начальным сочетанием `spec`."""
        super().__init__(parent)
        self._spec = ""
        self.setReadOnly(True)
        self.setPlaceholderText("Нажмите сочетание")
        self.setToolTip(
            "Поставьте курсор в поле и нажмите сочетание клавиш. "
            "Delete или Esc — очистить."
        )
        self.set_spec(spec)

    def spec(self) -> str:
        """Спецификация pynput (`<f5>`, `<ctrl>+<alt>+s`) или пустая строка."""
        return self._spec

    def set_spec(self, spec: str) -> None:
        """Показать сочетание в поле (без испускания сигнала, если не изменилось)."""
        changed = spec != self._spec
        self._spec = spec
        self.setText(spec_to_text(spec))
        if changed:
            self.spec_changed.emit(spec)

    def set_error(self, message: str | None) -> None:
        """Подсветить поле ошибкой и показать подсказку."""
        self.setProperty("invalid", bool(message))
        if message:
            self.setToolTip(message)
        else:
            self.setToolTip(
                "Поставьте курсор в поле и нажмите сочетание клавиш. "
                "Delete или Esc — очистить."
            )
        style = self.style()
        style.unpolish(self)
        style.polish(self)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 — имя из Qt
        """Записать нажатое сочетание вместо обычного ввода текста."""
        key = event.key()
        if key in _MODIFIER_KEYS:
            event.accept()
            return

        no_modifiers = event.modifiers() == Qt.KeyboardModifier.NoModifier
        if no_modifiers and key in (
            Qt.Key.Key_Escape,
            Qt.Key.Key_Delete,
            Qt.Key.Key_Backspace,
        ):
            self._set_recorded("")
            event.accept()
            return

        sequence = _sequence_from_event(event)
        spec = sequence_to_spec(sequence) if sequence else None
        problem = (
            "Это сочетание нельзя назначить: нужна клавиша вместе с Ctrl, Alt или Win"
            if spec is None
            else spec_problem(spec)
        )
        if problem is not None:
            self.set_error(problem)
            event.accept()
            return

        self.set_error(None)
        self._set_recorded(spec)
        event.accept()

    def _set_recorded(self, spec: str) -> None:
        """Записать новую спецификацию и уведомить подписчиков."""
        self.set_error(None)
        self._spec = spec
        self.setText(spec_to_text(spec))
        self.spec_changed.emit(spec)


def _sequence_from_event(event: QKeyEvent) -> str:
    """Собрать строку вида `Ctrl+Alt+S` из события Qt."""
    modifiers = event.modifiers()
    parts: list[str] = []
    if modifiers & Qt.KeyboardModifier.ControlModifier:
        parts.append("Ctrl")
    if modifiers & Qt.KeyboardModifier.AltModifier:
        parts.append("Alt")
    if modifiers & Qt.KeyboardModifier.ShiftModifier:
        parts.append("Shift")
    if modifiers & Qt.KeyboardModifier.MetaModifier:
        parts.append("Meta")

    key = event.key()
    if key == Qt.Key.Key_Plus:
        parts.append("+")
    else:
        key_text = QKeySequence(key).toString(QKeySequence.SequenceFormat.PortableText)
        if not key_text:
            return ""
        parts.append(key_text)
    return "+".join(parts)
