"""Настройки приложения: модель, значения по умолчанию, JSON в %APPDATA%."""

import json
import logging
import os
from collections.abc import Mapping
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

#: Версия формата файла настроек (при несовместимых изменениях — увеличить).
SETTINGS_VERSION = 1

#: Допустимые кнопки мыши (значения `core.input.backend.Button`).
ALLOWED_BUTTONS: tuple[str, ...] = ("left", "right", "middle")

#: Допустимые действия при закрытии окна.
ALLOWED_CLOSE_ACTIONS: tuple[str, ...] = ("ask", "tray", "quit")

#: Границы координат: запас под несколько мониторов и отрицательные координаты.
MIN_COORDINATE = -32_768
MAX_COORDINATE = 32_767

#: Границы интервала (мс) и числа повторов.
MIN_INTERVAL_MS = 1
MAX_INTERVAL_MS = 3_600_000
MIN_REPEATS = 1
MAX_REPEATS = 1_000_000_000

#: Имя файла настроек.
SETTINGS_FILENAME = "settings.json"


def _clamp_int(value: int, low: int, high: int, default: int) -> int:
    """Привести целое к диапазону `[low, high]`; нечисловое — к `default`."""
    if not isinstance(value, int) or isinstance(value, bool):
        return default
    return max(low, min(high, value))


def _pick_str(value: str, allowed: tuple[str, ...], default: str) -> str:
    """Вернуть `value`, если оно входит в `allowed`, иначе `default`."""
    if not isinstance(value, str):
        return default
    return value if value in allowed else default


def _pick_hotkey(value: str, default: str) -> str:
    """Вернуть хоткей, если это непустая строка, иначе `default`."""
    if not isinstance(value, str):
        return default
    stripped = value.strip()
    return stripped or default


@dataclass
class Settings:
    """Пользовательские настройки («Простой режим» и поведение окна).

    Все поля имеют безопасные значения по умолчанию: настройки можно
    сохранять и загружать без предварительной валидации — `normalized()`
    приводит их к допустимому виду.
    """

    x: int = 0
    y: int = 0
    button: str = "left"
    interval_ms: int = 100
    repeats: int = 100
    infinite: bool = False
    hotkey_start: str = "<f5>"
    hotkey_stop: str = "<f6>"
    hotkey_pick: str = "<f8>"
    close_action_running: str = "ask"
    close_action_idle: str = "ask"

    def normalized(self) -> "Settings":
        """Вернуть копию с проверенными и приведёнными к диапазонам значениями."""
        infinite = self.infinite if isinstance(self.infinite, bool) else False
        return Settings(
            x=_clamp_int(self.x, MIN_COORDINATE, MAX_COORDINATE, 0),
            y=_clamp_int(self.y, MIN_COORDINATE, MAX_COORDINATE, 0),
            button=_pick_str(self.button, ALLOWED_BUTTONS, "left"),
            interval_ms=_clamp_int(
                self.interval_ms,
                MIN_INTERVAL_MS,
                MAX_INTERVAL_MS,
                Settings.interval_ms,
            ),
            repeats=_clamp_int(
                self.repeats, MIN_REPEATS, MAX_REPEATS, Settings.repeats
            ),
            infinite=infinite,
            hotkey_start=_pick_hotkey(self.hotkey_start, Settings.hotkey_start),
            hotkey_stop=_pick_hotkey(self.hotkey_stop, Settings.hotkey_stop),
            hotkey_pick=_pick_hotkey(self.hotkey_pick, Settings.hotkey_pick),
            close_action_running=_pick_str(
                self.close_action_running,
                ALLOWED_CLOSE_ACTIONS,
                "ask",
            ),
            close_action_idle=_pick_str(
                self.close_action_idle,
                ALLOWED_CLOSE_ACTIONS,
                "ask",
            ),
        )

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "Settings":
        """Собрать настройки из словаря: неизвестные ключи и типы игнорируются."""
        result = cls()
        for field in fields(cls):
            if field.name not in data:
                continue
            raw = data[field.name]
            default = getattr(result, field.name)
            if isinstance(default, bool):
                value = raw if isinstance(raw, bool) else default
            elif isinstance(default, int):
                value = (
                    raw
                    if isinstance(raw, int) and not isinstance(raw, bool)
                    else default
                )
            elif isinstance(default, str):
                value = raw if isinstance(raw, str) else default
            else:  # pragma: no cover — защита от новых типов полей
                value = default
            setattr(result, field.name, value)
        return result

    def to_mapping(self) -> dict[str, Any]:
        """Словарь для JSON: поля настроек + версия формата."""
        return {"version": SETTINGS_VERSION, **asdict(self.normalized())}


class SettingsStore:
    """Загрузка и сохранение настроек в JSON-файл.

    Файл пишется атомарно (временный файл + `os.replace`), ошибки чтения
    и записи не пробрасываются наружу: приложение продолжает работать
    на значениях по умолчанию.
    """

    def __init__(self, path: Path | None = None) -> None:
        """Создать хранилище; `path=None` — путь по умолчанию в `%APPDATA%`."""
        self._path = Path(path) if path is not None else self.default_path()

    @property
    def path(self) -> Path:
        """Путь к файлу настроек."""
        return self._path

    @staticmethod
    def default_path() -> Path:
        """Путь по умолчанию: `%APPDATA%\\ClicKit\\settings.json`."""
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) if appdata else Path.home() / ".config"
        return base / "ClicKit" / SETTINGS_FILENAME

    def load(self) -> Settings:
        """Прочитать настройки; при любой проблеме — значения по умолчанию."""
        try:
            raw_text = self._path.read_text(encoding="utf-8")
        except FileNotFoundError:
            logger.info("Файл настроек не найден, используются значения по умолчанию")
            return Settings()
        except OSError:
            logger.warning(
                "Не удалось прочитать настройки %s", self._path, exc_info=True
            )
            return Settings()

        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError:
            logger.warning(
                "Файл настроек повреждён, используются значения по умолчанию"
            )
            return Settings()

        if not isinstance(data, dict):
            logger.warning("Файл настроек имеет неверный формат, используются дефолты")
            return Settings()

        return Settings.from_mapping(data).normalized()

    def save(self, settings: Settings) -> None:
        """Сохранить настройки атомарно; ошибка записи только логируется."""
        payload = settings.to_mapping()
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = self._path.with_name(self._path.name + ".tmp")
            tmp_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            os.replace(tmp_path, self._path)
        except OSError:
            logger.warning(
                "Не удалось сохранить настройки %s", self._path, exc_info=True
            )
