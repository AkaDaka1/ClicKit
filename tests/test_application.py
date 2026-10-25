"""Тесты точки входа: стартовые настройки приложения (без запуска event loop)."""

from pathlib import Path

from app.application import initial_settings
from core.settings import Settings, SettingsStore


def test_first_launch_uses_screen_center(tmp_path: Path) -> None:
    """Первый запуск: точка клика — центр экрана, а не (0, 0)."""
    store = SettingsStore(tmp_path / "settings.json")

    settings = initial_settings(store, (683, 384))

    assert (settings.x, settings.y) == (683, 384)


def test_saved_point_wins_over_center(tmp_path: Path) -> None:
    """Сохранённая точка не перезаписывается центром экрана."""
    store = SettingsStore(tmp_path / "settings.json")
    store.save(Settings(x=10, y=20))

    settings = initial_settings(store, (683, 384))

    assert (settings.x, settings.y) == (10, 20)


def test_no_screen_falls_back_to_defaults(tmp_path: Path) -> None:
    """Без информации об экране используются значения по умолчанию."""
    store = SettingsStore(tmp_path / "settings.json")

    settings = initial_settings(store, None)

    defaults = Settings()
    assert (settings.x, settings.y) == (defaults.x, defaults.y)
