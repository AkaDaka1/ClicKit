"""Тесты темы оформления: разрешение режима, QSS, менеджер темы (offscreen)."""

from PySide6.QtWidgets import QApplication

from core.settings import Settings
from gui.theme import (
    ThemeManager,
    resolve_theme,
    stylesheet_for,
    system_is_dark,
    theme_path,
)


def test_explicit_modes_ignore_system() -> None:
    """Явно выбранная тема не зависит от системной."""
    assert resolve_theme("dark", system_is_dark=False) == "dark"
    assert resolve_theme("light", system_is_dark=True) == "light"


def test_system_mode_follows_system() -> None:
    """Режим «системная» повторяет схему Windows."""
    assert resolve_theme("system", system_is_dark=True) == "dark"
    assert resolve_theme("system", system_is_dark=False) == "light"


def test_unknown_mode_is_system() -> None:
    """Неизвестный режим трактуется как системный, а не падает."""
    assert resolve_theme("neon", system_is_dark=True) == "dark"
    assert resolve_theme("", system_is_dark=False) == "light"


def test_theme_files_exist_and_are_not_empty() -> None:
    """У обеих тем есть QSS с общими селекторами."""
    for theme in ("dark", "light"):
        text = stylesheet_for(theme)
        assert text, f"пустой файл темы {theme}"
        assert "QPushButton#primary" in text


def test_theme_paths_differ() -> None:
    """Тёмная и светлая темы читаются из разных файлов."""
    assert theme_path("dark").name == "dark.qss"
    assert theme_path("light").name == "light.qss"
    assert theme_path("unknown") == theme_path("dark")


def test_theme_manager_applies_and_switches(qt_app: object) -> None:
    """Менеджер ставит QSS приложению и сообщает о смене темы."""
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    manager = ThemeManager("dark")
    events: list[str] = []
    manager.changed.connect(events.append)

    manager.apply(app)
    assert manager.effective == "dark"
    assert "background-color: #1e1f22" in app.styleSheet()
    assert events == ["dark"]

    manager.set_mode("light")
    assert manager.mode == "light"
    assert manager.effective == "light"
    assert "background-color: #f4f5f7" in app.styleSheet()
    assert events == ["dark", "light"]

    # Повторная установка того же режима не дёргает подписчиков.
    manager.set_mode("light")
    assert events == ["dark", "light"]
    manager.set_mode("neon")
    assert manager.mode == "system"


def test_theme_manager_keeps_effective_in_system_mode(qt_app: object) -> None:
    """В системном режиме действующая тема совпадает с системной схемой."""
    manager = ThemeManager(Settings().theme)

    assert manager.effective == resolve_theme("system", system_is_dark())
