"""Тема оформления: режим из настроек → конкретная тема GUI и Blockly.

Настройка хранит только режим (`system`/`dark`/`light`). Разрешение режима
в конкретную тему (`dark`/`light`) происходит в одном месте — здесь,
поэтому окно и холст Blockly никогда не расходятся.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from app.paths import resource_path
from core.settings import ALLOWED_THEMES

logger = logging.getLogger(__name__)

#: Режим темы, который хранится в настройках.
DEFAULT_THEME_MODE = "system"

#: Имена файлов QSS в `resources/styles/`.
_THEME_FILES = {"dark": "dark.qss", "light": "light.qss"}

#: Запасная тема, если системная схема неизвестна (оформление M2).
_FALLBACK_THEME = "dark"


def resolve_theme(mode: str, system_is_dark: bool) -> str:
    """Разрешить режим настройки в конкретную тему `dark` или `light`.

    Args:
        mode: `system`, `dark` или `light`; неизвестное значение — `system`.
        system_is_dark: тёмная ли сейчас системная тема Windows.
    """
    if mode == "dark":
        return "dark"
    if mode == "light":
        return "light"
    return "dark" if system_is_dark else "light"


def system_is_dark() -> bool:
    """Тёмная ли системная тема; неизвестную схему считаем тёмной."""
    hints = QGuiApplication.styleHints()
    color_scheme = getattr(hints, "colorScheme", None)
    if color_scheme is None:  # pragma: no cover — Qt старше 6.5
        return _FALLBACK_THEME == "dark"
    try:
        value = color_scheme()
    except TypeError:  # pragma: no cover — свойство вместо метода
        value = color_scheme
    return bool(value != Qt.ColorScheme.Light)


def theme_path(theme: str) -> Path:
    """Путь к QSS-файлу темы (`dark.qss` или `light.qss`)."""
    filename = _THEME_FILES.get(theme, _THEME_FILES[_FALLBACK_THEME])
    return resource_path("styles", filename)


def stylesheet_for(theme: str) -> str:
    """Прочитать QSS темы; при ошибке — пустая строка (стиль по умолчанию)."""
    try:
        return theme_path(theme).read_text(encoding="utf-8")
    except OSError:
        logger.warning("Не удалось загрузить тему %s", theme, exc_info=True)
        return ""


class ThemeManager(QObject):
    """Единственный владелец действующей темы приложения.

    Сигналы:
        changed: действующая тема (`dark`/`light`) изменилась.
    """

    changed = Signal(str)

    def __init__(
        self, mode: str = DEFAULT_THEME_MODE, parent: QObject | None = None
    ) -> None:
        """Создать менеджер темы с режимом из настроек."""
        super().__init__(parent)
        self._mode = mode if mode in ALLOWED_THEMES else DEFAULT_THEME_MODE
        self._app: QApplication | None = None
        self._effective = resolve_theme(self._mode, system_is_dark())

        hints = QGuiApplication.styleHints()
        if hasattr(hints, "colorSchemeChanged"):
            hints.colorSchemeChanged.connect(self._on_system_scheme_changed)

    @property
    def mode(self) -> str:
        """Режим из настроек (`system`/`dark`/`light`)."""
        return self._mode

    @property
    def effective(self) -> str:
        """Действующая тема (`dark`/`light`)."""
        return self._effective

    def apply(self, app: QApplication) -> None:
        """Применить текущую тему к приложению и уведомить подписчиков."""
        self._app = app
        self._effective = resolve_theme(self._mode, system_is_dark())
        self._apply()
        self.changed.emit(self._effective)

    def set_mode(self, mode: str) -> None:
        """Сменить режим темы и сразу применить, если приложение уже создано."""
        self._mode = mode if mode in ALLOWED_THEMES else DEFAULT_THEME_MODE
        effective = resolve_theme(self._mode, system_is_dark())
        if effective == self._effective:
            return
        self._effective = effective
        self._apply()
        self.changed.emit(self._effective)

    def _apply(self) -> None:
        """Передать QSS приложению (если оно уже создано)."""
        if self._app is not None:
            self._app.setStyleSheet(stylesheet_for(self._effective))

    def _on_system_scheme_changed(self) -> None:
        """Системная тема Windows изменилась — пересчитать в режиме `system`."""
        if self._mode != DEFAULT_THEME_MODE:
            return
        effective = resolve_theme(self._mode, system_is_dark())
        if effective == self._effective:
            return
        self._effective = effective
        self._apply()
        self.changed.emit(self._effective)
