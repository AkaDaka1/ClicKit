"""Тесты IR-схемы: разбор, сериализация и валидация."""

import json
from typing import Any

import pytest

from core.input.backend import Button
from core.ir.nodes import (
    ClickNode,
    DelayNode,
    DoubleClickNode,
    DragNode,
    IfNode,
    KeyNode,
    LoopNode,
    MoveNode,
    ScrollNode,
    SequenceNode,
)
from core.ir.schema import (
    MAX_NODES,
    ScenarioValidationError,
    scenario_from_json,
    scenario_from_mapping,
)


def base_payload(nodes: list[dict[str, Any]]) -> dict[str, Any]:
    """Минимальный корректный сценарий с заданными узлами."""
    return {"version": 1, "nodes": nodes}


def test_all_node_types_round_trip() -> None:
    """Все типы узлов разбираются и сохраняются без потерь."""
    payload = {
        "version": 1,
        "name": "Все узлы",
        "nodes": [
            {"type": "click", "id": "c1", "x": 10, "y": 20},
            {"type": "double_click", "x": 10, "y": 20, "button": "right"},
            {"type": "move", "x": 30, "y": 40, "duration": 0.25},
            {"type": "drag", "x": 50, "y": 60, "button": "middle"},
            {"type": "delay", "seconds": 1.5},
            {"type": "key", "keys": "CTRL + S"},
            {"type": "scroll", "amount": -5},
            {"type": "scroll", "amount": 3, "x": 1, "y": 2},
            {
                "type": "loop",
                "times": None,
                "children": [{"type": "delay", "seconds": 0}],
            },
            {
                "type": "sequence",
                "children": [
                    {"type": "key", "keys": "f5"},
                    {"type": "key", "keys": "enter"},
                ],
            },
            {
                "type": "if",
                "condition": {"kind": "pixel", "x": 1, "y": 2},
                "then": [{"type": "click", "x": 3, "y": 4}],
                "else": [],
            },
        ],
    }

    scenario = scenario_from_mapping(payload)

    assert isinstance(scenario.nodes[0], ClickNode)
    assert scenario.nodes[0].id == "c1"
    assert scenario.nodes[0].button is Button.LEFT
    assert isinstance(scenario.nodes[1], DoubleClickNode)
    assert scenario.nodes[1].button is Button.RIGHT
    assert isinstance(scenario.nodes[2], MoveNode)
    assert scenario.nodes[2].duration == 0.25
    assert isinstance(scenario.nodes[3], DragNode)
    assert scenario.nodes[3].duration == 0.5
    assert scenario.nodes[3].button is Button.MIDDLE
    assert isinstance(scenario.nodes[4], DelayNode)
    assert isinstance(scenario.nodes[5], KeyNode)
    assert scenario.nodes[5].keys == "ctrl + s"
    assert isinstance(scenario.nodes[6], ScrollNode)
    assert scenario.nodes[6].x is None
    assert isinstance(scenario.nodes[8], LoopNode)
    assert scenario.nodes[8].times is None
    assert isinstance(scenario.nodes[9], SequenceNode)
    assert isinstance(scenario.nodes[10], IfNode)

    assert scenario_from_mapping(scenario.to_mapping()) == scenario


def test_serialization_keeps_infinite_loop_and_omits_none() -> None:
    """`times: null` сохраняется, необязательные `id`/координаты — нет."""
    scenario = scenario_from_mapping(
        base_payload(
            [
                {
                    "type": "loop",
                    "times": None,
                    "children": [{"type": "key", "keys": "a"}],
                },
                {"type": "scroll", "amount": 1},
            ]
        )
    )

    mapping = scenario.to_mapping()

    assert mapping["nodes"][0]["times"] is None
    assert "id" not in mapping["nodes"][0]
    assert "x" not in mapping["nodes"][1]
    assert "y" not in mapping["nodes"][1]


def test_unknown_keys_are_ignored() -> None:
    """Неизвестные ключи (задел на совместимость) не мешают разбору."""
    scenario = scenario_from_mapping(
        {
            "version": 1,
            "future": {"a": 1},
            "nodes": [{"type": "click", "x": 1, "y": 2, "future": True}],
        }
    )

    assert scenario.nodes[0].x == 1


def test_scenario_from_json_reads_text() -> None:
    """Текст JSON разбирается как и словарь."""
    scenario = scenario_from_json(
        json.dumps(base_payload([{"type": "delay", "seconds": 0.1}]))
    )

    assert isinstance(scenario.nodes[0], DelayNode)


def test_invalid_json_reports_position() -> None:
    """Битый JSON — ошибка с номером строки и столбца."""
    with pytest.raises(ScenarioValidationError) as info:
        scenario_from_json('{"version": 1, "nodes": [')

    assert info.value.issues[0].path == "$"
    assert "строк" in info.value.issues[0].message


@pytest.mark.parametrize(
    ("payload", "expected_path"),
    [
        ({}, "version"),
        ({"nodes": [{"type": "delay", "seconds": 1}]}, "version"),
        ({"version": 2, "nodes": [{"type": "delay", "seconds": 1}]}, "version"),
        ({"version": "1", "nodes": [{"type": "delay", "seconds": 1}]}, "version"),
        ({"version": 1}, "nodes"),
        ({"version": 1, "nodes": []}, "nodes"),
        ({"version": 1, "nodes": "click"}, "nodes"),
        ({"version": 1, "nodes": [42]}, "nodes[0]"),
        ({"version": 1, "nodes": [{"x": 1, "y": 2}]}, "nodes[0]"),
        ({"version": 1, "nodes": [{"type": "nope"}]}, "nodes[0]"),
        ({"version": 1, "nodes": [{"type": "click", "x": 1}]}, "nodes[0].y"),
        (
            {"version": 1, "nodes": [{"type": "click", "x": 999_999, "y": 2}]},
            "nodes[0].x",
        ),
        (
            {"version": 1, "nodes": [{"type": "click", "x": True, "y": 2}]},
            "nodes[0].x",
        ),
        (
            {"version": 1, "nodes": [{"type": "click", "x": 1, "y": 2, "button": "x"}]},
            "nodes[0].button",
        ),
        (
            {"version": 1, "nodes": [{"type": "move", "x": 1, "y": 2, "duration": 61}]},
            "nodes[0].duration",
        ),
        (
            {"version": 1, "nodes": [{"type": "delay", "seconds": -1}]},
            "nodes[0].seconds",
        ),
        ({"version": 1, "nodes": [{"type": "key"}]}, "nodes[0].keys"),
        ({"version": 1, "nodes": [{"type": "key", "keys": "  "}]}, "nodes[0].keys"),
        (
            {"version": 1, "nodes": [{"type": "key", "keys": "hyper+z"}]},
            "nodes[0].keys",
        ),
        (
            {"version": 1, "nodes": [{"type": "key", "keys": "ctrl++s"}]},
            "nodes[0].keys",
        ),
        (
            {"version": 1, "nodes": [{"type": "scroll", "amount": 101}]},
            "nodes[0].amount",
        ),
        (
            {"version": 1, "nodes": [{"type": "scroll", "amount": 1, "x": 5}]},
            "nodes[0].x",
        ),
        ({"version": 1, "nodes": [{"type": "loop", "children": []}]}, "nodes[0].times"),
        (
            {"version": 1, "nodes": [{"type": "loop", "times": 0, "children": []}]},
            "nodes[0].times",
        ),
        (
            {"version": 1, "nodes": [{"type": "loop", "times": "3", "children": []}]},
            "nodes[0].times",
        ),
        (
            {"version": 1, "nodes": [{"type": "loop", "times": 2}]},
            "nodes[0].children",
        ),
        (
            {"version": 1, "nodes": [{"type": "sequence", "children": []}]},
            "nodes[0].children",
        ),
        (
            {"version": 1, "nodes": [{"type": "if", "then": []}]},
            "nodes[0].condition",
        ),
        (
            {"version": 1, "nodes": [{"type": "if", "condition": "x"}]},
            "nodes[0].condition",
        ),
    ],
)
def test_validation_errors(payload: dict[str, Any], expected_path: str) -> None:
    """Ошибки валидации указывают путь до проблемного поля."""
    with pytest.raises(ScenarioValidationError) as info:
        scenario_from_mapping(payload)

    paths = [issue.path for issue in info.value.issues]
    assert any(expected_path in path for path in paths), paths


def test_multiple_errors_are_collected() -> None:
    """За один раз показываются все найденные ошибки."""
    with pytest.raises(ScenarioValidationError) as info:
        scenario_from_mapping(
            base_payload(
                [
                    {"type": "click", "x": "a"},
                    {"type": "delay", "seconds": "b"},
                ]
            )
        )

    assert len(info.value.issues) >= 3


def test_duplicate_and_invalid_ids() -> None:
    """`id` должен быть уникальным и непустым."""
    duplicate = base_payload(
        [
            {"type": "delay", "seconds": 0, "id": "same"},
            {"type": "delay", "seconds": 0, "id": "same"},
        ]
    )
    with pytest.raises(ScenarioValidationError) as info:
        scenario_from_mapping(duplicate)
    assert any("повторяющийся id" in issue.message for issue in info.value.issues)

    empty = base_payload([{"type": "delay", "seconds": 0, "id": "  "}])
    with pytest.raises(ScenarioValidationError):
        scenario_from_mapping(empty)


def test_depth_limit() -> None:
    """Слишком глубокая вложенность отклоняется."""
    node: dict[str, Any] = {"type": "click", "x": 1, "y": 1}
    for _ in range(40):
        node = {"type": "sequence", "children": [node]}

    with pytest.raises(ScenarioValidationError) as info:
        scenario_from_mapping(base_payload([node]))

    assert any("глубина" in issue.message for issue in info.value.issues)


def test_node_limit() -> None:
    """Слишком много узлов отклоняется."""
    nodes = [{"type": "delay", "seconds": 0} for _ in range(MAX_NODES + 1)]

    with pytest.raises(ScenarioValidationError) as info:
        scenario_from_mapping(base_payload(nodes))

    assert any("лимит узлов" in issue.message for issue in info.value.issues)
