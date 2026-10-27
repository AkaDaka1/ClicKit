"""Трансляция Blockly-JSON ↔ IR-сценарий.

Модуль не зависит от Qt и Blockly-рантайма: он работает с JSON, который
отдаёт `Blockly.serialization.workspaces.save`. Валидация значений выполняется
единственным источником правды — схемой IR (`core.ir.schema`), а ошибки
сопоставляются с конкретными блоками для подсветки в редакторе.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from core.ir.nodes import (
    SCENARIO_VERSION,
    ClickNode,
    DelayNode,
    DoubleClickNode,
    DragNode,
    IfNode,
    KeyNode,
    LoopNode,
    MoveNode,
    Node,
    Scenario,
    ScrollNode,
    SequenceNode,
)
from core.ir.schema import (
    MAX_DEPTH,
    MAX_NODES,
    ScenarioValidationError,
    ValidationIssue,
    scenario_from_mapping,
)

#: Префикс автоматически сгенерированных id для узлов без id.
AUTO_ID_PREFIX = "ck-auto-"


@dataclass(frozen=True)
class BlocklyIssue:
    """Проблема в Blockly-схеме или в получившемся IR.

    `block_id` — идентификатор блока Blockly для подсветки; `None`, если
    ошибка не привязана к конкретному блоку (например, пустой холст).
    """

    block_id: str | None
    message: str


class BlocklyTranslationError(ValueError):
    """Blockly-схему не удалось превратить в корректный IR-сценарий."""

    def __init__(self, issues: Sequence[BlocklyIssue]) -> None:
        """Сохранить список проблем и собрать читаемый текст."""
        self._issues = tuple(issues)
        lines = [issue.message for issue in self._issues]
        super().__init__(
            "Сценарий не удалось собрать из блоков:\n  " + "\n  ".join(lines)
        )

    @property
    def issues(self) -> tuple[BlocklyIssue, ...]:
        """Все найденные проблемы."""
        return self._issues


@dataclass(frozen=True)
class TranslationResult:
    """Результат трансляции: сценарий и предупреждения (не ошибки)."""

    scenario: Scenario
    warnings: tuple[BlocklyIssue, ...] = ()


# --- Blockly-JSON → IR -------------------------------------------------------


def workspace_to_scenario(
    workspace: Mapping[str, Any], name: str = ""
) -> TranslationResult:
    """Превратить сохранённый workspace Blockly в проверенный IR-сценарий.

    Raises:
        BlocklyTranslationError: холст пуст, есть неизвестные блоки или
            получившийся сценарий не проходит проверку IR.
    """
    translator = _Translator()
    blocks = _root_blocks(workspace, translator)
    nodes = translator.chain(blocks, depth=1)
    if translator.issues:
        raise BlocklyTranslationError(translator.issues)

    raw_mapping: dict[str, Any] = {
        "version": SCENARIO_VERSION,
        "name": name,
        "nodes": nodes,
    }
    try:
        scenario = scenario_from_mapping(raw_mapping)
    except ScenarioValidationError as exc:
        raise BlocklyTranslationError(
            _issues_from_schema(exc.issues, raw_mapping)
        ) from exc
    return TranslationResult(scenario=scenario, warnings=tuple(translator.warnings))


def _root_blocks(
    workspace: Mapping[str, Any], translator: _Translator
) -> list[Mapping[str, Any]]:
    """Достать список корневых блоков из JSON workspace."""
    if not isinstance(workspace, Mapping):
        raise BlocklyTranslationError(
            [BlocklyIssue(None, "Рабочая область повреждена")]
        )
    container = workspace.get("blocks")
    raw_blocks = container.get("blocks") if isinstance(container, Mapping) else None
    if not isinstance(raw_blocks, Sequence) or isinstance(raw_blocks, str):
        raise BlocklyTranslationError(
            [BlocklyIssue(None, "Рабочая область повреждена: нет списка блоков")]
        )
    if not raw_blocks:
        raise BlocklyTranslationError(
            [BlocklyIssue(None, "На холсте нет блоков — добавьте хотя бы один")]
        )

    blocks: list[Mapping[str, Any]] = []
    for raw in raw_blocks:
        if isinstance(raw, Mapping):
            blocks.append(raw)
        else:
            translator.issues.append(
                BlocklyIssue(None, "Повреждённый блок в рабочей области")
            )
    return blocks


class _Translator:
    """Состояние обхода дерева блоков и накопления проблем."""

    def __init__(self) -> None:
        self.issues: list[BlocklyIssue] = []
        self.warnings: list[BlocklyIssue] = []
        self.node_count = 0

    def chain(
        self, start_blocks: Sequence[Mapping[str, Any]], depth: int
    ) -> list[dict[str, Any]]:
        """Разобрать цепочки `next` на одном уровне (корень или тело цикла)."""
        result: list[dict[str, Any]] = []
        seen: set[int] = set()
        for start in start_blocks:
            current: Mapping[str, Any] | None = start
            while current is not None:
                marker = id(current)
                if marker in seen:
                    self.issues.append(
                        BlocklyIssue(_block_id(current), "Циклическая ссылка в блоках")
                    )
                    break
                seen.add(marker)
                if depth > MAX_DEPTH:
                    self.issues.append(
                        BlocklyIssue(
                            _block_id(current),
                            f"Слишком глубокая вложенность (максимум {MAX_DEPTH})",
                        )
                    )
                    break
                if _is_disabled(current):
                    self.warnings.append(
                        BlocklyIssue(
                            _block_id(current), "Отключённый блок не выполняется"
                        )
                    )
                else:
                    node = self._parse_block(current, depth)
                    if node is not None:
                        self.node_count += 1
                        if self.node_count > MAX_NODES:
                            self.issues.append(
                                BlocklyIssue(
                                    _block_id(current),
                                    f"Превышен лимит узлов ({MAX_NODES})",
                                )
                            )
                            break
                        result.append(node)
                current = _next_block(current)
        return result

    def _parse_block(
        self, block: Mapping[str, Any], depth: int
    ) -> dict[str, Any] | None:
        """Разобрать один блок; неизвестный тип — ошибка с id блока."""
        block_type = block.get("type")
        if not isinstance(block_type, str) or not block_type:
            self.issues.append(BlocklyIssue(_block_id(block), "У блока нет типа"))
            return None
        builder = _BUILDERS.get(block_type)
        if builder is None:
            self.issues.append(
                BlocklyIssue(
                    _block_id(block),
                    f"Неизвестный блок '{block_type}' — обновите редактор",
                )
            )
            return None
        return builder(block, self, depth)


_BlockBuilder = Callable[
    [Mapping[str, Any], _Translator, int],
    dict[str, Any] | None,
]


def _block_id(block: Mapping[str, Any]) -> str | None:
    """Вернуть id блока Blockly, если он задан строкой."""
    value = block.get("id")
    return value if isinstance(value, str) and value else None


def _next_block(block: Mapping[str, Any]) -> Mapping[str, Any] | None:
    """Следующий блок в цепочке `next`."""
    link = block.get("next")
    candidate = link.get("block") if isinstance(link, Mapping) else None
    return candidate if isinstance(candidate, Mapping) else None


def _is_disabled(block: Mapping[str, Any]) -> bool:
    """Отключён ли блок в Blockly (v13: `disabledReasons`)."""
    reasons = block.get("disabledReasons")
    if isinstance(reasons, Sequence) and not isinstance(reasons, str) and reasons:
        return True
    return block.get("disabled") is True


def _fields(block: Mapping[str, Any]) -> Mapping[str, Any]:
    """Поля блока (пустой словарь, если их нет)."""
    fields = block.get("fields")
    return fields if isinstance(fields, Mapping) else {}


def _as_int(value: Any) -> int | None:
    """Привести значение поля к int (Blockly может дать float)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(round(value))


def _as_float(value: Any) -> float | None:
    """Привести значение поля к float."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _node(
    block: Mapping[str, Any],
    node_type: str,
    **values: Any,
) -> dict[str, Any]:
    """Собрать IR-словарь узла: тип, id и заданные поля."""
    result: dict[str, Any] = {"type": node_type}
    block_id = _block_id(block)
    if block_id is not None:
        result["id"] = block_id
    for key, value in values.items():
        if value is not None:
            result[key] = value
    return result


def _statement_children(
    block: Mapping[str, Any],
    input_name: str,
    translator: _Translator,
    depth: int,
) -> list[dict[str, Any]]:
    """Разобрать цепочку внутри statement-входа (`DO`)."""
    inputs = block.get("inputs")
    statement = inputs.get(input_name) if isinstance(inputs, Mapping) else None
    first = statement.get("block") if isinstance(statement, Mapping) else None
    if not isinstance(first, Mapping):
        return []
    return translator.chain([first], depth + 1)


def _with_position(block: Mapping[str, Any], node_type: str) -> dict[str, Any]:
    """Узел с координатами `x`/`y` и полем кнопки, общий для мыши."""
    fields = _fields(block)
    return _node(
        block,
        node_type,
        x=_as_int(fields.get("X")),
        y=_as_int(fields.get("Y")),
        button=fields.get("BUTTON") if isinstance(fields.get("BUTTON"), str) else None,
    )


def _build_click(
    block: Mapping[str, Any], translator: _Translator, depth: int
) -> dict[str, Any]:
    """Блок одиночного клика."""
    return _with_position(block, "click")


def _build_double_click(
    block: Mapping[str, Any], translator: _Translator, depth: int
) -> dict[str, Any]:
    """Блок двойного клика."""
    return _with_position(block, "double_click")


def _build_move(
    block: Mapping[str, Any], translator: _Translator, depth: int
) -> dict[str, Any]:
    """Блок перемещения курсора."""
    fields = _fields(block)
    return _node(
        block,
        "move",
        x=_as_int(fields.get("X")),
        y=_as_int(fields.get("Y")),
        duration=_as_float(fields.get("DURATION")),
    )


def _build_drag(
    block: Mapping[str, Any], translator: _Translator, depth: int
) -> dict[str, Any]:
    """Блок перетаскивания."""
    fields = _fields(block)
    return _node(
        block,
        "drag",
        x=_as_int(fields.get("X")),
        y=_as_int(fields.get("Y")),
        duration=_as_float(fields.get("DURATION")),
        button=fields.get("BUTTON") if isinstance(fields.get("BUTTON"), str) else None,
    )


def _build_scroll(
    block: Mapping[str, Any], translator: _Translator, depth: int
) -> dict[str, Any]:
    """Блок прокрутки без точки."""
    fields = _fields(block)
    return _node(block, "scroll", amount=_as_int(fields.get("AMOUNT")))


def _build_scroll_at(
    block: Mapping[str, Any], translator: _Translator, depth: int
) -> dict[str, Any]:
    """Блок прокрутки в заданной точке."""
    fields = _fields(block)
    return _node(
        block,
        "scroll",
        amount=_as_int(fields.get("AMOUNT")),
        x=_as_int(fields.get("X")),
        y=_as_int(fields.get("Y")),
    )


def _build_key(
    block: Mapping[str, Any], translator: _Translator, depth: int
) -> dict[str, Any]:
    """Блок нажатия клавиш."""
    keys = _fields(block).get("KEYS")
    return _node(block, "key", keys=keys if isinstance(keys, str) else None)


def _build_delay(
    block: Mapping[str, Any], translator: _Translator, depth: int
) -> dict[str, Any]:
    """Блок паузы."""
    return _node(block, "delay", seconds=_as_float(_fields(block).get("SECONDS")))


def _build_loop(
    block: Mapping[str, Any], translator: _Translator, depth: int
) -> dict[str, Any]:
    """Блок «повторить N раз»."""
    return _node(
        block,
        "loop",
        times=_as_int(_fields(block).get("TIMES")),
        children=_statement_children(block, "DO", translator, depth),
    )


def _build_loop_forever(
    block: Mapping[str, Any], translator: _Translator, depth: int
) -> dict[str, Any]:
    """Блок «повторять бесконечно»."""
    node = _node(
        block,
        "loop",
        children=_statement_children(block, "DO", translator, depth),
    )
    # `None` нельзя передать через `_node`: он отбрасывает пустые поля,
    # а для бесконечного цикла `times: null` обязателен.
    node["times"] = None
    return node


_BUILDERS: dict[str, _BlockBuilder] = {
    "ck_click": _build_click,
    "ck_double_click": _build_double_click,
    "ck_move": _build_move,
    "ck_drag": _build_drag,
    "ck_scroll": _build_scroll,
    "ck_scroll_at": _build_scroll_at,
    "ck_key": _build_key,
    "ck_delay": _build_delay,
    "ck_loop": _build_loop,
    "ck_loop_forever": _build_loop_forever,
}


# --- ошибки схемы → блоки ----------------------------------------------------

_PATH_TOKEN = re.compile(r"([a-z_]+)(?:\[(\d+)\])?")
_CHILD_KEYS = frozenset({"children", "then", "else"})


def _node_id_for_path(mapping: Mapping[str, Any], path: str) -> str | None:
    """Найти id узла по пути ошибки IR (`nodes[2].children[0].x`)."""
    nodes = mapping.get("nodes")
    if not isinstance(nodes, list):
        return None
    current: Any = nodes
    last_id: str | None = None
    for token in path.split("."):
        match = _PATH_TOKEN.fullmatch(token)
        if match is None:
            return last_id
        name = match.group(1)
        index = match.group(2)
        if name == "nodes":
            if not isinstance(current, list) or index is None:
                return last_id
            current = _safe_item(current, int(index))
        elif name in _CHILD_KEYS:
            if not isinstance(current, Mapping) or index is None:
                return last_id
            children = current.get(name)
            if not isinstance(children, list):
                return last_id
            current = _safe_item(children, int(index))
        else:
            return _node_id(current, last_id)
        if isinstance(current, Mapping):
            last_id = _node_id(current, last_id)
    return last_id


def _safe_item(items: Sequence[Any], index: int) -> Any:
    """Элемент списка или `None`, если индекса нет."""
    return items[index] if 0 <= index < len(items) else None


def _node_id(node: Any, fallback: str | None) -> str | None:
    """id узла, если это словарь с непустой строкой `id`."""
    if isinstance(node, Mapping):
        value = node.get("id")
        if isinstance(value, str) and value:
            return value
    return fallback


def _issues_from_schema(
    issues: Sequence[ValidationIssue], mapping: Mapping[str, Any]
) -> list[BlocklyIssue]:
    """Сопоставить ошибки IR-схемы с блоками Blockly."""
    result: list[BlocklyIssue] = []
    for issue in issues:
        block_id = _node_id_for_path(mapping, issue.path)
        message = (
            issue.message if block_id is not None else f"{issue.path}: {issue.message}"
        )
        result.append(BlocklyIssue(block_id, message))
    return result


# --- IR → Blockly-JSON -------------------------------------------------------


def scenario_to_workspace(scenario: Scenario) -> dict[str, Any]:
    """Собрать JSON workspace Blockly из IR-сценария.

    Координаты блоков не задаются: после загрузки редактор вызывает
    `workspace.cleanUp()` и раскладывает блоки автоматически. Узел `sequence`
    разворачивается в текущий стек, поэтому отдельного блока для него нет.
    """
    generator = _IdGenerator(scenario)
    block = _build_chain_block(_flatten(scenario.nodes), generator)
    return {
        "blocks": {
            "languageVersion": 0,
            "blocks": [block] if block is not None else [],
        }
    }


class _IdGenerator:
    """Выдаёт id блокам, у которых в IR не было id."""

    def __init__(self, scenario: Scenario) -> None:
        self._used = {
            node.id for node in _iter_nodes(scenario.nodes) if node.id is not None
        }
        self._counter = 0

    def id_for(self, node: Node) -> str:
        """id узла или новый уникальный автоматический id."""
        if node.id:
            return node.id
        while True:
            self._counter += 1
            candidate = f"{AUTO_ID_PREFIX}{self._counter}"
            if candidate not in self._used:
                self._used.add(candidate)
                return candidate


def _iter_nodes(nodes: Sequence[Node]) -> Iterator[Node]:
    """Обойти все узлы, включая вложенные."""
    for node in nodes:
        yield node
        if isinstance(node, SequenceNode):
            yield from _iter_nodes(node.children)
        elif isinstance(node, LoopNode):
            yield from _iter_nodes(node.children)
        elif isinstance(node, IfNode):
            yield from _iter_nodes(node.then)
            yield from _iter_nodes(node.otherwise)


def _flatten(nodes: Sequence[Node]) -> list[Node]:
    """Развернуть `sequence` в плоский список, сохранив порядок."""
    result: list[Node] = []
    for node in nodes:
        if isinstance(node, SequenceNode):
            result.extend(_flatten(node.children))
        else:
            result.append(node)
    return result


def _build_chain_block(
    nodes: Sequence[Node], generator: _IdGenerator
) -> dict[str, Any] | None:
    """Построить цепочку блоков (`next`) из плоского списка узлов."""
    if not nodes:
        return None
    first = _node_to_block(nodes[0], generator)
    current = first
    for node in nodes[1:]:
        following = _node_to_block(node, generator)
        current["next"] = {"block": following}
        current = following
    return first


def _node_to_block(node: Node, generator: _IdGenerator) -> dict[str, Any]:
    """Превратить один IR-узел в блок Blockly."""
    block_id = generator.id_for(node)
    if isinstance(node, ClickNode):
        return {
            "type": "ck_click",
            "id": block_id,
            "fields": {"X": node.x, "Y": node.y, "BUTTON": node.button.value},
        }
    if isinstance(node, DoubleClickNode):
        return {
            "type": "ck_double_click",
            "id": block_id,
            "fields": {"X": node.x, "Y": node.y, "BUTTON": node.button.value},
        }
    if isinstance(node, MoveNode):
        return {
            "type": "ck_move",
            "id": block_id,
            "fields": {"X": node.x, "Y": node.y, "DURATION": node.duration},
        }
    if isinstance(node, DragNode):
        return {
            "type": "ck_drag",
            "id": block_id,
            "fields": {
                "X": node.x,
                "Y": node.y,
                "DURATION": node.duration,
                "BUTTON": node.button.value,
            },
        }
    if isinstance(node, ScrollNode):
        if node.x is None or node.y is None:
            return {
                "type": "ck_scroll",
                "id": block_id,
                "fields": {"AMOUNT": node.amount},
            }
        return {
            "type": "ck_scroll_at",
            "id": block_id,
            "fields": {"AMOUNT": node.amount, "X": node.x, "Y": node.y},
        }
    if isinstance(node, DelayNode):
        return {
            "type": "ck_delay",
            "id": block_id,
            "fields": {"SECONDS": node.seconds},
        }
    if isinstance(node, KeyNode):
        return {
            "type": "ck_key",
            "id": block_id,
            "fields": {"KEYS": node.keys},
        }
    if isinstance(node, LoopNode):
        block: dict[str, Any] = {
            "type": "ck_loop" if node.times is not None else "ck_loop_forever",
            "id": block_id,
        }
        if node.times is not None:
            block["fields"] = {"TIMES": node.times}
        body = _build_chain_block(_flatten(node.children), generator)
        if body is not None:
            block["inputs"] = {"DO": {"block": body}}
        return block
    if isinstance(node, IfNode):
        raise BlocklyTranslationError(
            [
                BlocklyIssue(
                    node.id,
                    "Узел 'if' пока не поддерживается редактором — "
                    "условия появятся в следующих версиях",
                )
            ]
        )
    raise BlocklyTranslationError(
        [BlocklyIssue(node.id, f"Узел {type(node).__name__} не поддерживается")]
    )
