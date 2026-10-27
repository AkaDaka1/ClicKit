"""Гибридный файл сценария: IR-часть и сохранённое состояние редактора Blockly.

`.acl.json` остаётся корректным IR-файлом (его читают CLI и старые версии),
а необязательное поле `editor.workspace` хранит точное состояние холста.
Источник истины для исполнения — `nodes`; при расхождении (файл правили
вручную) блоки восстанавливаются из IR.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bridge.blockly_ir import (
    BlocklyTranslationError,
    scenario_to_workspace,
    workspace_to_scenario,
)
from core.ir.nodes import Scenario
from core.ir.schema import (
    ScenarioValidationError,
    ValidationIssue,
    scenario_from_mapping,
)
from core.ir.storage import ScenarioFileError, write_json

logger = logging.getLogger(__name__)

#: Значение `editor.kind` для редактора Blockly.
EDITOR_KIND = "blockly"


@dataclass(frozen=True)
class ScenarioDocument:
    """Сценарий и необязательное состояние редактора Blockly."""

    scenario: Scenario
    workspace: dict[str, Any] | None = None


def load_document(path: str | Path) -> ScenarioDocument:
    """Прочитать сценарий и состояние редактора из файла.

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

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        issue = ValidationIssue(
            "$",
            f"файл не является корректным JSON: {exc.msg} "
            f"(строка {exc.lineno}, столбец {exc.colno})",
        )
        raise ScenarioValidationError([issue]) from exc

    scenario = scenario_from_mapping(data)
    return ScenarioDocument(scenario=scenario, workspace=_read_workspace(data))


def save_document(
    scenario: Scenario,
    path: str | Path,
    workspace: Mapping[str, Any] | None = None,
) -> Path:
    """Сохранить сценарий и (необязательно) состояние Blockly.

    Raises:
        ScenarioFileError: файл не удалось записать.
    """
    payload = scenario.to_mapping()
    if workspace is not None:
        payload["editor"] = {"kind": EDITOR_KIND, "workspace": dict(workspace)}
    return write_json(path, payload)


def resolve_workspace(document: ScenarioDocument) -> tuple[dict[str, Any], bool]:
    """Выбрать состояние Blockly для открытия сценария.

    Returns:
        Пары `(Blockly-JSON, восстановлено_из_IR)`. Сохранённое состояние
        используется, только если оно даёт ровно тот же IR, что и `nodes`;
        иначе блоки строятся из IR (флаг `True`).
    """
    workspace = document.workspace
    if workspace is not None:
        try:
            translated = workspace_to_scenario(workspace, document.scenario.name)
        except BlocklyTranslationError:
            logger.info(
                "Сохранённое состояние Blockly невалидно — восстанавливаю из IR"
            )
        else:
            if translated.scenario.to_mapping() == document.scenario.to_mapping():
                return workspace, False
            logger.info("editor.workspace расходится с nodes — восстанавливаю из IR")
    return scenario_to_workspace(document.scenario), True


def _read_workspace(data: Any) -> dict[str, Any] | None:
    """Достать `editor.workspace`, если это объект Blockly нужного вида."""
    if not isinstance(data, Mapping):
        return None
    editor = data.get("editor")
    if not isinstance(editor, Mapping):
        return None
    kind = editor.get("kind")
    if kind not in (None, EDITOR_KIND):
        logger.warning("Неизвестный тип редактора %r — состояние пропущено", kind)
        return None
    workspace = editor.get("workspace")
    if isinstance(workspace, dict):
        return workspace
    if workspace is not None:
        logger.warning("Поле editor.workspace имеет неверный тип — пропущено")
    return None
