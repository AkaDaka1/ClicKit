"""Диалог настроек: тема оформления и глобальные хоткеи."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.hotkey_spec import FIELD_LABELS, validate_hotkeys
from core.settings import Settings
from gui.widgets.hotkey_edit import HotkeyEdit

#: Подписи режимов темы: значение настройки → текст.
THEME_LABELS: tuple[tuple[str, str], ...] = (
    ("system", "Как в системе"),
    ("dark", "Тёмная"),
    ("light", "Светлая"),
)


class SettingsDialog(QDialog):
    """Настройки приложения: тема и три глобальных хоткея.

    Диалог не сохраняет настройки сам: после `exec()` вызывающий код
    забирает значения через `theme_mode()` и `hotkeys()`.
    """

    def __init__(self, settings: Settings, parent: QWidget | None = None) -> None:
        """Создать диалог с текущими настройками."""
        super().__init__(parent)
        self._settings = settings.normalized()
        self._hotkey_edits: dict[str, HotkeyEdit] = {}

        self.setWindowTitle("Настройки ClicKit")
        self.setModal(True)
        self.setMinimumWidth(520)
        self._build_ui()
        self._load_settings()

    # --- построение интерфейса -------------------------------------------------

    def _build_ui(self) -> None:
        """Собрать группы «Оформление» и «Глобальные хоткеи»."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(14)

        layout.addWidget(self._build_appearance_group())
        layout.addWidget(self._build_hotkeys_group())

        self._error_label = QLabel("")
        self._error_label.setObjectName("message")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        layout.addWidget(self._error_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        ok_button.setText("Сохранить")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Отмена")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _build_appearance_group(self) -> QGroupBox:
        """Группа «Оформление»: режим темы."""
        group = QGroupBox("Оформление")
        form = QFormLayout(group)
        form.setSpacing(10)

        self._theme_combo = QComboBox()
        for value, label in THEME_LABELS:
            self._theme_combo.addItem(label, value)
        self._theme_combo.setToolTip(
            "«Как в системе» повторяет тему Windows, в том числе при её смене"
        )
        form.addRow("Тема:", self._theme_combo)
        return group

    def _build_hotkeys_group(self) -> QGroupBox:
        """Группа «Глобальные хоткеи»: старт, стоп, захват точки."""
        group = QGroupBox("Глобальные хоткеи")
        form = QFormLayout(group)
        form.setSpacing(10)

        for field, label in FIELD_LABELS.items():
            edit = HotkeyEdit()
            edit.setObjectName(f"hotkey-{field}")
            self._hotkey_edits[field] = edit
            form.addRow(f"{label}:", edit)

        hint = QLabel(
            "Хоткеи работают во всех приложениях. Поставьте курсор в поле "
            "и нажмите сочетание; Delete или Esc — очистить."
        )
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        form.addRow(hint)

        reset = QPushButton("Сбросить к F5 / F6 / F8")
        reset.clicked.connect(self.reset_hotkeys)
        form.addRow(reset)
        return group

    # --- данные ----------------------------------------------------------------

    def theme_mode(self) -> str:
        """Выбранный режим темы (`system`/`dark`/`light`)."""
        return str(self._theme_combo.currentData())

    def set_theme_mode(self, mode: str) -> None:
        """Показать режим темы в списке."""
        index = self._theme_combo.findData(mode)
        self._theme_combo.setCurrentIndex(index if index >= 0 else 0)

    def hotkeys(self) -> dict[str, str]:
        """Текущие спецификации хоткеев по полям (`start`/`stop`/`pick`)."""
        return {field: edit.spec() for field, edit in self._hotkey_edits.items()}

    def hotkey_edit(self, field: str) -> HotkeyEdit:
        """Поле хоткея для тестов и точечной настройки."""
        return self._hotkey_edits[field]

    def reset_hotkeys(self) -> None:
        """Вернуть хоткеи по умолчанию (F5/F6/F8) и снять ошибки."""
        defaults = Settings()
        for field, edit in self._hotkey_edits.items():
            edit.set_error(None)
            edit.set_spec(getattr(defaults, f"hotkey_{field}"))
        self._hide_error()

    # --- проверка и завершение -------------------------------------------------

    def accept(self) -> None:
        """Проверить хоткеи и закрыть диалог только при отсутствии ошибок."""
        problems = validate_hotkeys(self.hotkeys())
        for field, edit in self._hotkey_edits.items():
            edit.set_error(problems.get(field))

        if problems:
            first_field = next(iter(problems))
            self._hotkey_edits[first_field].setFocus()
            self._show_error(problems[first_field])
            return

        self._hide_error()
        super().accept()

    def _load_settings(self) -> None:
        """Показать значения из настроек."""
        self.set_theme_mode(self._settings.theme)
        for field, edit in self._hotkey_edits.items():
            edit.set_spec(getattr(self._settings, f"hotkey_{field}"))

    def _show_error(self, text: str) -> None:
        """Показать сообщение об ошибке под группами."""
        self._error_label.setText(text)
        self._error_label.setProperty("error", True)
        style = self._error_label.style()
        style.unpolish(self._error_label)
        style.polish(self._error_label)
        self._error_label.show()

    def _hide_error(self) -> None:
        """Спрятать сообщение об ошибке."""
        self._error_label.setText("")
        self._error_label.hide()
