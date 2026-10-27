"""Сохранение и загрузка сценариев в файлы `.acl.json`."""

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from core.ir.nodes import Scenario
from core.ir.schema import scenario_from_json

#: Окончание имени файла сценария.
SCENARIO_SUFFIX = ".acl.json"


class ScenarioFileError(Exception):
    """Файл сценария не удалось прочитать или записать."""


def default_scenarios_dir() -> Path:
    """Каталог сценариев по умолчанию: `%APPDATA%\\ClicKit\\scenarios`."""
    appdata = os.environ.get("APPDATA")
    base = Path(appdata) if appdata else Path.home() / ".config"
    return base / "ClicKit" / "scenarios"


def load_scenario(path: str | Path) -> Scenario:
    """Прочитать и проверить сценарий из файла.

    Raises:
        ScenarioFileError: файл не найден или не читается.
        ScenarioValidationError: содержимое не является корректным сценарием.
    """
    file = Path(path)
    try:
        text = file.read_text(encoding="utf-8")
    except OSError as exc:
        reason = exc.strerror or str(exc)
        raise ScenarioFileError(
            f"Не удалось прочитать сценарий {file}: {reason}"
        ) from exc
    return scenario_from_json(text)


def write_json(path: str | Path, payload: Mapping[str, Any]) -> Path:
    """Атомарно записать JSON-объект (временный файл + `os.replace`).

    Args:
        path: путь к файлу; родительские каталоги создаются.
        payload: JSON-совместимый словарь (например, `.acl.json`).

    Returns:
        Путь, по которому записан файл.

    Raises:
        ScenarioFileError: каталог или файл не удалось записать.
    """
    file = Path(path)
    try:
        file.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        tmp_path = file.with_name(file.name + ".tmp")
        tmp_path.write_text(text, encoding="utf-8")
        os.replace(tmp_path, file)
    except (OSError, TypeError, ValueError) as exc:
        reason = exc.strerror if isinstance(exc, OSError) and exc.strerror else str(exc)
        raise ScenarioFileError(
            f"Не удалось сохранить сценарий {file}: {reason}"
        ) from exc
    return file


def save_scenario(scenario: Scenario, path: str | Path) -> Path:
    """Сохранить сценарий атомарно (временный файл + `os.replace`).

    Args:
        scenario: проверенный сценарий.
        path: путь к файлу `.acl.json`; родительские каталоги создаются.

    Returns:
        Путь, по которому сохранён сценарий.

    Raises:
        ScenarioFileError: каталог или файл не удалось записать.
    """
    return write_json(path, scenario.to_mapping())
