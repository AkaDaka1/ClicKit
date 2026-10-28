"""Тесты настроек: значения по умолчанию, сохранение/загрузка, битые файлы."""

import json
from pathlib import Path

import pytest

from core.settings import (
    MAX_INTERVAL_MS,
    MIN_INTERVAL_MS,
    SETTINGS_VERSION,
    Settings,
    SettingsStore,
)


def make_store(tmp_path: Path) -> SettingsStore:
    """Хранилище с файлом во временном каталоге теста."""
    return SettingsStore(tmp_path / "settings.json")


def test_defaults_without_file(tmp_path: Path) -> None:
    """Файла нет — возвращаются значения по умолчанию."""
    store = make_store(tmp_path)
    assert store.load() == Settings()


def test_roundtrip_keeps_values(tmp_path: Path) -> None:
    """Сохранённые настройки читаются без изменений; в файле есть версия."""
    store = make_store(tmp_path)
    settings = Settings(
        x=1920,
        y=-120,
        button="right",
        interval_ms=250,
        repeats=5,
        infinite=True,
    )
    store.save(settings)

    assert store.path.exists()
    assert store.load() == settings

    payload = json.loads(store.path.read_text(encoding="utf-8"))
    assert payload["version"] == SETTINGS_VERSION


def test_close_actions_are_independent(tmp_path: Path) -> None:
    """Поведение при закрытии хранится для двух сценариев отдельно."""
    store = make_store(tmp_path)
    settings = Settings(close_action_running="tray", close_action_idle="quit")
    store.save(settings)

    loaded = store.load()
    assert loaded.close_action_running == "tray"
    assert loaded.close_action_idle == "quit"


def test_corrupt_file_returns_defaults(tmp_path: Path) -> None:
    """Повреждённый JSON не роняет приложение."""
    store = make_store(tmp_path)
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text("{это не json", encoding="utf-8")

    assert store.load() == Settings()


def test_non_dict_json_returns_defaults(tmp_path: Path) -> None:
    """JSON не-объект (например, список) тоже не принимается."""
    store = make_store(tmp_path)
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text("[1, 2, 3]", encoding="utf-8")

    assert store.load() == Settings()


def test_wrong_types_fall_back_to_defaults(tmp_path: Path) -> None:
    """Неверные типы полей заменяются значениями по умолчанию."""
    store = make_store(tmp_path)
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text(
        json.dumps({"x": "далеко", "button": "side", "infinite": "yes", "unknown": 1}),
        encoding="utf-8",
    )

    loaded = store.load()
    defaults = Settings()
    assert loaded.x == defaults.x
    assert loaded.button == defaults.button
    assert loaded.infinite == defaults.infinite


def test_values_are_clamped(tmp_path: Path) -> None:
    """Интервал и повторы приводятся к допустимым диапазонам."""
    store = make_store(tmp_path)
    store.save(Settings(interval_ms=MAX_INTERVAL_MS * 10, repeats=0))

    loaded = store.load()
    assert loaded.interval_ms == MAX_INTERVAL_MS
    assert loaded.repeats == 1


def test_invalid_values_normalized() -> None:
    """`normalized()` отбрасывает недопустимые действия и пустые хоткеи."""
    settings = Settings(
        interval_ms=0,
        button="side",
        hotkey_start="   ",
        close_action_idle="explode",
        theme="neon",
    ).normalized()

    assert settings.interval_ms == MIN_INTERVAL_MS
    assert settings.button == "left"
    assert settings.hotkey_start == Settings.hotkey_start
    assert settings.close_action_idle == "ask"
    assert settings.theme == "system"


def test_old_settings_without_theme_get_system(tmp_path: Path) -> None:
    """Файл версии 1 (без поля theme) читается с темой «системная»."""
    store = make_store(tmp_path)
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text(
        json.dumps({"version": 1, "x": 10, "y": 20}), encoding="utf-8"
    )

    loaded = store.load()

    assert (loaded.x, loaded.y) == (10, 20)
    assert loaded.theme == "system"


def test_theme_roundtrip(tmp_path: Path) -> None:
    """Выбранная тема сохраняется и читается."""
    store = make_store(tmp_path)
    store.save(Settings(theme="light"))

    assert store.load().theme == "light"


def test_save_leaves_no_temp_file(tmp_path: Path) -> None:
    """Атомарная запись не оставляет временных файлов."""
    store = make_store(tmp_path)
    store.save(Settings())

    assert sorted(path.name for path in tmp_path.iterdir()) == ["settings.json"]


def test_default_path_uses_appdata(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """По умолчанию настройки лежат в `%APPDATA%\\ClicKit`."""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert SettingsStore.default_path() == tmp_path / "ClicKit" / "settings.json"
