"""Валидация IR-сценария и разбор JSON в типизированные узлы."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from core.input.backend import Button
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
from core.settings import ALLOWED_BUTTONS, MAX_COORDINATE, MIN_COORDINATE

#: Сколько ошибок показывать за один раз (остальные отбрасываются).
MAX_ISSUES = 50
#: Максимальное число узлов в сценарии (защита от случайных гигантских файлов).
MAX_NODES = 10_000
#: Максимальная глубина вложенности контейнеров.
MAX_DEPTH = 32
#: Ограничения полей узлов.
MAX_LOOP_TIMES = 1_000_000
MAX_DELAY_SECONDS = 3_600.0
MAX_MOVE_DURATION = 60.0
MIN_SCROLL_AMOUNT = -100
MAX_SCROLL_AMOUNT = 100
MAX_NAME_LENGTH = 200
MAX_ID_LENGTH = 64
MAX_KEYS_LENGTH = 64

#: Клавиши, которые понимает pyautogui (кроме одиночных печатных символов).
ALLOWED_KEY_NAMES: frozenset[str] = frozenset(
    {
        "alt",
        "altgr",
        "apps",
        "backspace",
        "break",
        "browserback",
        "browserforward",
        "browserhome",
        "browserrefresh",
        "browserstop",
        "capslock",
        "clear",
        "command",
        "ctrl",
        "delete",
        "down",
        "end",
        "enter",
        "esc",
        "escape",
        "help",
        "home",
        "insert",
        "left",
        "menu",
        "nexttrack",
        "numlock",
        "option",
        "pagedown",
        "pageup",
        "pause",
        "playpause",
        "prevtrack",
        "print",
        "printscreen",
        "return",
        "right",
        "scrolllock",
        "select",
        "shift",
        "space",
        "stop",
        "tab",
        "up",
        "volumedown",
        "volumemute",
        "volumeup",
        "win",
        "winleft",
        "winright",
    }
) | frozenset(f"f{number}" for number in range(1, 25))


@dataclass(frozen=True)
class ValidationIssue:
    """Одна ошибка проверки: путь до поля и понятное описание."""

    path: str
    message: str


class ScenarioValidationError(ValueError):
    """Сценарий не прошёл проверку; содержит все найденные ошибки."""

    def __init__(self, issues: Sequence[ValidationIssue]) -> None:
        """Сохранить список ошибок и собрать читаемый текст."""
        self._issues = tuple(issues)
        super().__init__(self._describe())

    @property
    def issues(self) -> tuple[ValidationIssue, ...]:
        """Все найденные ошибки (не больше `MAX_ISSUES`)."""
        return self._issues

    def _describe(self) -> str:
        """Текст исключения: по строке на ошибку."""
        lines = [f"{issue.path}: {issue.message}" for issue in self._issues]
        return "Сценарий не прошёл проверку:\n  " + "\n  ".join(lines)


class _Issues:
    """Накопитель ошибок и счётчиков обхода дерева."""

    def __init__(self) -> None:
        self.items: list[ValidationIssue] = []
        self.node_count = 0
        self.ids: set[str] = set()

    def add(self, path: str, message: str) -> None:
        """Добавить ошибку, если лимит ещё не исчерпан."""
        if len(self.items) < MAX_ISSUES:
            self.items.append(ValidationIssue(path, message))

    def full(self) -> bool:
        """Достигнут ли лимит показанных ошибок."""
        return len(self.items) >= MAX_ISSUES


_NodeParser = Callable[
    [Mapping[str, Any], str, _Issues, str | None, int],
    Node | None,
]


def scenario_from_mapping(data: Any) -> Scenario:
    """Разобрать и проверить сценарий из словаря; ошибки — исключением."""
    issues = _Issues()
    scenario = _build_scenario(data, issues)
    if issues.items:
        raise ScenarioValidationError(issues.items)
    return scenario


def scenario_from_json(text: str) -> Scenario:
    """Разобрать сценарий из текста JSON; ошибки — исключением."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        issue = ValidationIssue(
            "$",
            f"файл не является корректным JSON: {exc.msg} "
            f"(строка {exc.lineno}, столбец {exc.colno})",
        )
        raise ScenarioValidationError([issue]) from exc
    return scenario_from_mapping(data)


def _build_scenario(data: Any, issues: _Issues) -> Scenario:
    """Собрать сценарий; при ошибках возвращается пустая заготовка."""
    if not isinstance(data, Mapping):
        issues.add("$", "сценарий должен быть JSON-объектом")
        return Scenario(nodes=())
    version = _parse_version(data, issues)
    name = _parse_name(data, issues)
    raw_nodes = data.get("nodes")
    if not isinstance(raw_nodes, list):
        issues.add("nodes", "должно быть списком узлов")
        nodes: tuple[Node, ...] = ()
    elif not raw_nodes:
        issues.add("nodes", "должен содержать хотя бы один узел")
        nodes = ()
    else:
        nodes = _parse_nodes(raw_nodes, "nodes", issues, 1)
    if issues.items:
        return Scenario(nodes=())
    return Scenario(nodes=nodes, name=name, version=version)


def _parse_version(data: Mapping[str, Any], issues: _Issues) -> int:
    """Проверить версию формата; отсутствие/несовпадение — ошибка."""
    if "version" not in data:
        issues.add("version", f"нет обязательного поля (ожидается {SCENARIO_VERSION})")
        return SCENARIO_VERSION
    value = data["version"]
    if not isinstance(value, int) or isinstance(value, bool):
        issues.add("version", "должно быть целым числом")
        return SCENARIO_VERSION
    if value != SCENARIO_VERSION:
        issues.add(
            "version",
            f"неподдерживаемая версия {value} "
            f"(поддерживается только {SCENARIO_VERSION})",
        )
    return value


def _parse_name(data: Mapping[str, Any], issues: _Issues) -> str:
    """Проверить необязательное имя сценария."""
    if "name" not in data:
        return ""
    value = data["name"]
    if not isinstance(value, str):
        issues.add("name", "должно быть строкой")
        return ""
    value = value.strip()
    if len(value) > MAX_NAME_LENGTH:
        issues.add("name", f"длиннее {MAX_NAME_LENGTH} символов")
        return ""
    return value


def _parse_nodes(
    raw_nodes: Sequence[Any],
    path: str,
    issues: _Issues,
    depth: int,
) -> tuple[Node, ...]:
    """Разобрать список узлов одного уровня вложенности."""
    if depth > MAX_DEPTH:
        issues.add(path, f"превышена максимальная глубина вложенности ({MAX_DEPTH})")
        return ()
    result: list[Node] = []
    for index, raw in enumerate(raw_nodes):
        if issues.full():
            break
        node = _parse_node(raw, f"{path}[{index}]", issues, depth)
        if node is not None:
            result.append(node)
    return tuple(result)


def _parse_node(
    raw: Any,
    path: str,
    issues: _Issues,
    depth: int,
) -> Node | None:
    """Разобрать один узел по его `type`; при ошибке вернуть `None`."""
    if not isinstance(raw, Mapping):
        issues.add(path, "узел должен быть JSON-объектом")
        return None
    node_type = raw.get("type")
    if not isinstance(node_type, str) or not node_type.strip():
        issues.add(path, "поле 'type' должно быть непустой строкой")
        return None
    parser = _PARSERS.get(node_type)
    if parser is None:
        supported = ", ".join(sorted(_PARSERS))
        issues.add(path, f"неизвестный тип узла '{node_type}' ({supported})")
        return None

    before = len(issues.items)
    node_id = _parse_id(raw, path, issues)
    if len(issues.items) > before:
        return None
    issues.node_count += 1
    if issues.node_count > MAX_NODES:
        issues.add(path, f"превышен лимит узлов ({MAX_NODES})")
        return None
    return parser(raw, path, issues, node_id, depth)


def _parse_id(raw: Mapping[str, Any], path: str, issues: _Issues) -> str | None:
    """Проверить необязательный стабильный идентификатор узла."""
    if "id" not in raw:
        return None
    value = raw["id"]
    if not isinstance(value, str) or not value.strip():
        issues.add(f"{path}.id", "должен быть непустой строкой")
        return None
    value = value.strip()
    if len(value) > MAX_ID_LENGTH:
        issues.add(f"{path}.id", f"длиннее {MAX_ID_LENGTH} символов")
        return None
    if value in issues.ids:
        issues.add(f"{path}.id", f"повторяющийся id '{value}'")
        return None
    issues.ids.add(value)
    return value


def _require_int(
    raw: Mapping[str, Any],
    name: str,
    path: str,
    issues: _Issues,
    low: int,
    high: int,
) -> int | None:
    """Прочитать обязательное целое поле с диапазоном."""
    if name not in raw:
        issues.add(f"{path}.{name}", f"нет обязательного поля '{name}'")
        return None
    value = raw[name]
    if not isinstance(value, int) or isinstance(value, bool):
        issues.add(f"{path}.{name}", "должно быть целым числом")
        return None
    if not low <= value <= high:
        issues.add(f"{path}.{name}", f"должно быть от {low} до {high}")
        return None
    return value


def _optional_int(
    raw: Mapping[str, Any],
    name: str,
    path: str,
    issues: _Issues,
    low: int,
    high: int,
    default: int | None = None,
) -> int | None:
    """Прочитать необязательное целое поле с диапазоном."""
    if name not in raw:
        return default
    return _require_int(raw, name, path, issues, low, high)


def _require_number(
    raw: Mapping[str, Any],
    name: str,
    path: str,
    issues: _Issues,
    low: float,
    high: float,
) -> float | None:
    """Прочитать обязательное число (int/float) с диапазоном."""
    if name not in raw:
        issues.add(f"{path}.{name}", f"нет обязательного поля '{name}'")
        return None
    return _check_number(raw[name], f"{path}.{name}", issues, low, high)


def _optional_number(
    raw: Mapping[str, Any],
    name: str,
    path: str,
    issues: _Issues,
    low: float,
    high: float,
    default: float,
) -> float:
    """Прочитать необязательное число с диапазоном."""
    if name not in raw:
        return default
    value = _check_number(raw[name], f"{path}.{name}", issues, low, high)
    return default if value is None else value


def _check_number(
    value: Any,
    path: str,
    issues: _Issues,
    low: float,
    high: float,
) -> float | None:
    """Проверить число и вернуть его как float."""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        issues.add(path, "должно быть числом")
        return None
    value = float(value)
    if not low <= value <= high:
        issues.add(path, f"должно быть от {low:g} до {high:g}")
        return None
    return value


def _optional_button(raw: Mapping[str, Any], path: str, issues: _Issues) -> Button:
    """Прочитать кнопку мыши (по умолчанию — левая)."""
    if "button" not in raw:
        return Button.LEFT
    value = raw["button"]
    if value not in ALLOWED_BUTTONS:
        allowed = ", ".join(ALLOWED_BUTTONS)
        issues.add(f"{path}.button", f"должно быть одним из: {allowed}")
        return Button.LEFT
    return Button(value)


def _require_keys(
    raw: Mapping[str, Any],
    path: str,
    issues: _Issues,
) -> str | None:
    """Прочитать и проверить комбинацию клавиш."""
    if "keys" not in raw:
        issues.add(f"{path}.keys", "нет обязательного поля 'keys'")
        return None
    value = raw["keys"]
    if not isinstance(value, str):
        issues.add(f"{path}.keys", "должно быть строкой")
        return None
    value = value.strip().lower()
    if not value:
        issues.add(f"{path}.keys", "не может быть пустым")
        return None
    if len(value) > MAX_KEYS_LENGTH:
        issues.add(f"{path}.keys", f"длиннее {MAX_KEYS_LENGTH} символов")
        return None
    for part in value.split("+"):
        part = part.strip()
        valid_char = len(part) == 1 and part.isprintable()
        if not part or not (part in ALLOWED_KEY_NAMES or valid_char):
            issues.add(
                f"{path}.keys",
                f"неизвестная клавиша '{part}' (примеры: ctrl+s, f5, enter)",
            )
            return None
    return value


def _parse_children(
    raw: Mapping[str, Any],
    path: str,
    issues: _Issues,
    depth: int,
) -> tuple[Node, ...] | None:
    """Прочитать обязательный непустой список дочерних узлов."""
    if "children" not in raw:
        issues.add(f"{path}.children", "нет обязательного поля 'children'")
        return None
    children = raw["children"]
    if not isinstance(children, list):
        issues.add(f"{path}.children", "должно быть списком узлов")
        return None
    if not children:
        issues.add(f"{path}.children", "должен содержать хотя бы один узел")
        return None
    return _parse_nodes(children, f"{path}.children", issues, depth + 1)


def _parse_click(
    raw: Mapping[str, Any],
    path: str,
    issues: _Issues,
    node_id: str | None,
    depth: int,
) -> ClickNode | None:
    """Разобрать узел `click`."""
    x = _require_int(raw, "x", path, issues, MIN_COORDINATE, MAX_COORDINATE)
    y = _require_int(raw, "y", path, issues, MIN_COORDINATE, MAX_COORDINATE)
    button = _optional_button(raw, path, issues)
    if x is None or y is None:
        return None
    return ClickNode(id=node_id, x=x, y=y, button=button)


def _parse_double_click(
    raw: Mapping[str, Any],
    path: str,
    issues: _Issues,
    node_id: str | None,
    depth: int,
) -> DoubleClickNode | None:
    """Разобрать узел `double_click`."""
    x = _require_int(raw, "x", path, issues, MIN_COORDINATE, MAX_COORDINATE)
    y = _require_int(raw, "y", path, issues, MIN_COORDINATE, MAX_COORDINATE)
    button = _optional_button(raw, path, issues)
    if x is None or y is None:
        return None
    return DoubleClickNode(id=node_id, x=x, y=y, button=button)


def _parse_move(
    raw: Mapping[str, Any],
    path: str,
    issues: _Issues,
    node_id: str | None,
    depth: int,
) -> MoveNode | None:
    """Разобрать узел `move`."""
    x = _require_int(raw, "x", path, issues, MIN_COORDINATE, MAX_COORDINATE)
    y = _require_int(raw, "y", path, issues, MIN_COORDINATE, MAX_COORDINATE)
    duration = _optional_number(
        raw, "duration", path, issues, 0.0, MAX_MOVE_DURATION, 0.0
    )
    if x is None or y is None:
        return None
    return MoveNode(id=node_id, x=x, y=y, duration=duration)


def _parse_drag(
    raw: Mapping[str, Any],
    path: str,
    issues: _Issues,
    node_id: str | None,
    depth: int,
) -> DragNode | None:
    """Разобрать узел `drag`."""
    x = _require_int(raw, "x", path, issues, MIN_COORDINATE, MAX_COORDINATE)
    y = _require_int(raw, "y", path, issues, MIN_COORDINATE, MAX_COORDINATE)
    duration = _optional_number(
        raw, "duration", path, issues, 0.0, MAX_MOVE_DURATION, 0.5
    )
    button = _optional_button(raw, path, issues)
    if x is None or y is None:
        return None
    return DragNode(id=node_id, x=x, y=y, duration=duration, button=button)


def _parse_delay(
    raw: Mapping[str, Any],
    path: str,
    issues: _Issues,
    node_id: str | None,
    depth: int,
) -> DelayNode | None:
    """Разобрать узел `delay`."""
    seconds = _require_number(raw, "seconds", path, issues, 0.0, MAX_DELAY_SECONDS)
    if seconds is None:
        return None
    return DelayNode(id=node_id, seconds=seconds)


def _parse_key(
    raw: Mapping[str, Any],
    path: str,
    issues: _Issues,
    node_id: str | None,
    depth: int,
) -> KeyNode | None:
    """Разобрать узел `key`."""
    keys = _require_keys(raw, path, issues)
    if keys is None:
        return None
    return KeyNode(id=node_id, keys=keys)


def _parse_scroll(
    raw: Mapping[str, Any],
    path: str,
    issues: _Issues,
    node_id: str | None,
    depth: int,
) -> ScrollNode | None:
    """Разобрать узел `scroll` (координаты — только обе или ни одной)."""
    amount = _require_int(
        raw, "amount", path, issues, MIN_SCROLL_AMOUNT, MAX_SCROLL_AMOUNT
    )
    has_x = "x" in raw
    has_y = "y" in raw
    if has_x != has_y:
        issues.add(f"{path}.x", "укажите и x, и y, либо не указывайте ни одного")
        return None
    if not has_x:
        return None if amount is None else ScrollNode(id=node_id, amount=amount)
    x = _require_int(raw, "x", path, issues, MIN_COORDINATE, MAX_COORDINATE)
    y = _require_int(raw, "y", path, issues, MIN_COORDINATE, MAX_COORDINATE)
    if amount is None or x is None or y is None:
        return None
    return ScrollNode(id=node_id, amount=amount, x=x, y=y)


def _parse_loop(
    raw: Mapping[str, Any],
    path: str,
    issues: _Issues,
    node_id: str | None,
    depth: int,
) -> LoopNode | None:
    """Разобрать узел `loop`: `times` (int или null) и `children`."""
    before = len(issues.items)
    times = _parse_times(raw, path, issues)
    children = _parse_children(raw, path, issues, depth)
    if len(issues.items) > before or children is None:
        return None
    return LoopNode(id=node_id, times=times, children=children)


def _parse_times(
    raw: Mapping[str, Any],
    path: str,
    issues: _Issues,
) -> int | None:
    """Прочитать `times`: число повторов или `null` (до остановки)."""
    if "times" not in raw:
        issues.add(
            f"{path}.times",
            "нет обязательного поля 'times' (null — до остановки)",
        )
        return None
    value = raw["times"]
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        issues.add(f"{path}.times", "должно быть целым числом или null")
        return None
    if not 1 <= value <= MAX_LOOP_TIMES:
        issues.add(f"{path}.times", f"должно быть от 1 до {MAX_LOOP_TIMES} или null")
        return None
    return value


def _parse_sequence(
    raw: Mapping[str, Any],
    path: str,
    issues: _Issues,
    node_id: str | None,
    depth: int,
) -> SequenceNode | None:
    """Разобрать узел `sequence` — группу узлов."""
    children = _parse_children(raw, path, issues, depth)
    if children is None:
        return None
    return SequenceNode(id=node_id, children=children)


def _parse_if(
    raw: Mapping[str, Any],
    path: str,
    issues: _Issues,
    node_id: str | None,
    depth: int,
) -> IfNode | None:
    """Разобрать зарезервированный узел `if` (исполнение — в будущих версиях)."""
    before = len(issues.items)
    condition = _parse_condition(raw, path, issues)
    then = _parse_optional_children(raw, "then", path, issues, depth)
    otherwise = _parse_optional_children(raw, "else", path, issues, depth)
    if len(issues.items) > before or condition is None:
        return None
    return IfNode(
        id=node_id,
        condition=condition,
        then=then,
        otherwise=otherwise,
    )


def _parse_condition(
    raw: Mapping[str, Any],
    path: str,
    issues: _Issues,
) -> dict[str, Any] | None:
    """Проверить структуру условия (содержимое — задача будущих версий)."""
    if "condition" not in raw:
        issues.add(f"{path}.condition", "нет обязательного поля 'condition'")
        return None
    value = raw["condition"]
    if not isinstance(value, Mapping):
        issues.add(f"{path}.condition", "должно быть JSON-объектом")
        return None
    return dict(value)


def _parse_optional_children(
    raw: Mapping[str, Any],
    name: str,
    path: str,
    issues: _Issues,
    depth: int,
) -> tuple[Node, ...]:
    """Прочитать необязательный список дочерних узлов (`then`/`else`)."""
    if name not in raw:
        return ()
    value = raw[name]
    if not isinstance(value, list):
        issues.add(f"{path}.{name}", "должно быть списком узлов")
        return ()
    return _parse_nodes(value, f"{path}.{name}", issues, depth + 1)


_PARSERS: dict[str, _NodeParser] = {
    ClickNode.type: _parse_click,
    DoubleClickNode.type: _parse_double_click,
    MoveNode.type: _parse_move,
    DragNode.type: _parse_drag,
    DelayNode.type: _parse_delay,
    KeyNode.type: _parse_key,
    ScrollNode.type: _parse_scroll,
    LoopNode.type: _parse_loop,
    SequenceNode.type: _parse_sequence,
    IfNode.type: _parse_if,
}
