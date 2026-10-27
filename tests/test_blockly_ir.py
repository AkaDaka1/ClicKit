"""Тесты трансляции Blockly-JSON ↔ IR."""

from typing import Any

import pytest

from bridge.blockly_ir import (
    AUTO_ID_PREFIX,
    BlocklyIssue,
    BlocklyTranslationError,
    scenario_to_workspace,
    workspace_to_scenario,
)
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
    Scenario,
    ScrollNode,
    SequenceNode,
)

# --- вспомогательные построители Blockly-JSON --------------------------------


def block(
    block_type: str,
    *,
    block_id: str | None = None,
    fields: dict[str, Any] | None = None,
    inputs: dict[str, Any] | None = None,
    next_block: dict[str, Any] | None = None,
    disabled: bool = False,
) -> dict[str, Any]:
    """Собрать блок в формате Blockly-сериализации."""
    result: dict[str, Any] = {"type": block_type}
    if block_id is not None:
        result["id"] = block_id
    if fields:
        result["fields"] = fields
    if inputs:
        result["inputs"] = inputs
    if next_block is not None:
        result["next"] = {"block": next_block}
    if disabled:
        result["disabledReasons"] = ["MANUALLY_DISABLED"]
    return result


def workspace(*blocks: dict[str, Any]) -> dict[str, Any]:
    """Собрать JSON workspace."""
    return {"blocks": {"languageVersion": 0, "blocks": list(blocks)}}


def chain(*blocks: dict[str, Any]) -> dict[str, Any]:
    """Связать блоки через `next` (возвращает первый)."""
    for current, following in zip(blocks, blocks[1:], strict=False):
        current["next"] = {"block": following}
    return blocks[0]


def statement(block_value: dict[str, Any]) -> dict[str, Any]:
    """Оформить блок как содержимое statement-входа."""
    return {"block": block_value}


def click(
    block_id: str,
    x: int = 10,
    y: int = 20,
    button: str = "left",
    *,
    disabled: bool = False,
):
    """Блок клика."""
    return block(
        "ck_click",
        block_id=block_id,
        fields={"X": x, "Y": y, "BUTTON": button},
        disabled=disabled,
    )


# --- Blockly → IR ------------------------------------------------------------


def test_all_block_types_translate() -> None:
    """Каждый тип блока превращается в правильный IR-узел."""
    body = click("loop-click", 1, 2)
    tree = chain(
        click("c1", 400, 300, "right"),
        block(
            "ck_double_click",
            block_id="d1",
            fields={"X": 10, "Y": 20, "BUTTON": "left"},
        ),
        block(
            "ck_move",
            block_id="m1",
            fields={"X": 30, "Y": 40, "DURATION": 0.2},
        ),
        block(
            "ck_drag",
            block_id="g1",
            fields={"X": 50, "Y": 60, "DURATION": 0.7, "BUTTON": "middle"},
        ),
        block("ck_scroll", block_id="s1", fields={"AMOUNT": 3}),
        block(
            "ck_scroll_at",
            block_id="s2",
            fields={"AMOUNT": -4, "X": 70, "Y": 80},
        ),
        block("ck_key", block_id="k1", fields={"KEYS": "ctrl+s"}),
        block("ck_delay", block_id="t1", fields={"SECONDS": 0.5}),
        block(
            "ck_loop",
            block_id="l1",
            fields={"TIMES": 2},
            inputs={"DO": statement(body)},
        ),
        block(
            "ck_loop_forever",
            block_id="l2",
            inputs={"DO": statement(block("ck_delay", fields={"SECONDS": 1}))},
        ),
    )

    result = workspace_to_scenario(workspace(tree), "Тест")
    nodes = result.scenario.nodes

    assert [node.type for node in nodes] == [
        "click",
        "double_click",
        "move",
        "drag",
        "scroll",
        "scroll",
        "key",
        "delay",
        "loop",
        "loop",
    ]
    assert [node.id for node in nodes] == [
        "c1",
        "d1",
        "m1",
        "g1",
        "s1",
        "s2",
        "k1",
        "t1",
        "l1",
        "l2",
    ]

    first = nodes[0]
    assert isinstance(first, ClickNode)
    assert (first.x, first.y, first.button) == (400, 300, Button.RIGHT)

    move = nodes[2]
    assert isinstance(move, MoveNode)
    assert (move.x, move.y, move.duration) == (30, 40, 0.2)

    drag = nodes[3]
    assert isinstance(drag, DragNode)
    assert (drag.button, drag.duration) == (Button.MIDDLE, 0.7)

    scroll_plain = nodes[4]
    assert isinstance(scroll_plain, ScrollNode)
    assert (scroll_plain.amount, scroll_plain.x, scroll_plain.y) == (3, None, None)

    scroll_at = nodes[5]
    assert isinstance(scroll_at, ScrollNode)
    assert (scroll_at.amount, scroll_at.x, scroll_at.y) == (-4, 70, 80)

    key = nodes[6]
    assert isinstance(key, KeyNode)
    assert key.keys == "ctrl+s"

    delay = nodes[7]
    assert isinstance(delay, DelayNode)
    assert delay.seconds == 0.5

    loop = nodes[8]
    assert isinstance(loop, LoopNode)
    assert loop.times == 2
    assert [child.id for child in loop.children] == ["loop-click"]

    forever = nodes[9]
    assert isinstance(forever, LoopNode)
    assert forever.times is None
    assert result.scenario.name == "Тест"
    assert result.warnings == ()


def test_defaults_and_rounding() -> None:
    """Необязательные поля берут значения по умолчанию, числа округляются."""
    tree = chain(
        block("ck_click", block_id="c", fields={"X": 10.6, "Y": 20.4}),
        block("ck_drag", block_id="d", fields={"X": 1, "Y": 2}),
        block(
            "ck_loop",
            block_id="l",
            fields={"TIMES": 2.4},
            inputs={"DO": statement(block("ck_delay", fields={"SECONDS": 1}))},
        ),
    )
    scenario = workspace_to_scenario(workspace(tree)).scenario

    clicked = scenario.nodes[0]
    assert isinstance(clicked, ClickNode)
    assert (clicked.x, clicked.y, clicked.button) == (11, 20, Button.LEFT)

    dragged = scenario.nodes[1]
    assert isinstance(dragged, DragNode)
    assert dragged.duration == 0.5
    assert dragged.button is Button.LEFT

    loop = scenario.nodes[2]
    assert isinstance(loop, LoopNode)
    assert loop.times == 2


def test_statement_chain_preserves_order() -> None:
    """Внутри цикла несколько блоков идут в порядке цепочки `next`."""
    body = chain(
        block("ck_move", block_id="m", fields={"X": 1, "Y": 2}),
        click("c", 3, 4),
    )
    tree = block(
        "ck_loop",
        block_id="l",
        fields={"TIMES": 3},
        inputs={"DO": statement(body)},
    )
    loop = workspace_to_scenario(workspace(tree)).scenario.nodes[0]

    assert isinstance(loop, LoopNode)
    assert [child.type for child in loop.children] == ["move", "click"]


def test_disabled_block_is_skipped_with_warning() -> None:
    """Отключённый блок не попадает в сценарий, но даёт предупреждение."""
    tree = chain(
        click("off", disabled=True),
        block("ck_delay", block_id="on", fields={"SECONDS": 1}),
    )
    result = workspace_to_scenario(workspace(tree))

    assert [node.id for node in result.scenario.nodes] == ["on"]
    assert len(result.warnings) == 1
    assert result.warnings[0] == BlocklyIssue("off", "Отключённый блок не выполняется")


def test_unknown_block_reports_block_id() -> None:
    """Неизвестный тип блока — ошибка с id для подсветки."""
    with pytest.raises(BlocklyTranslationError) as excinfo:
        workspace_to_scenario(workspace(block("controls_repeat_ext", block_id="x")))

    assert excinfo.value.issues[0].block_id == "x"
    assert "Неизвестный блок" in excinfo.value.issues[0].message


def test_empty_workspace_is_error() -> None:
    """Пустой холст не превращается в пустой сценарий."""
    with pytest.raises(BlocklyTranslationError) as excinfo:
        workspace_to_scenario(workspace())

    assert excinfo.value.issues[0].block_id is None
    assert "нет блоков" in excinfo.value.issues[0].message


def test_empty_loop_body_points_to_loop_block() -> None:
    """Пустое тело цикла — ошибка с id самого блока цикла."""
    tree = block("ck_loop", block_id="loop-1", fields={"TIMES": 2})
    with pytest.raises(BlocklyTranslationError) as excinfo:
        workspace_to_scenario(workspace(tree))

    issue = excinfo.value.issues[0]
    assert issue.block_id == "loop-1"
    assert "хотя бы один узел" in issue.message


def test_invalid_coordinate_points_to_nested_block() -> None:
    """Ошибка схемы во вложенном блоке сопоставляется с его id."""
    tree = block(
        "ck_loop",
        block_id="outer",
        fields={"TIMES": 1},
        inputs={
            "DO": statement(
                block("ck_click", block_id="inner", fields={"X": 999_999, "Y": 1})
            )
        },
    )
    with pytest.raises(BlocklyTranslationError) as excinfo:
        workspace_to_scenario(workspace(tree))

    issue = excinfo.value.issues[0]
    assert issue.block_id == "inner"
    assert "от -32768 до 32767" in issue.message


def test_invalid_keys_points_to_key_block() -> None:
    """Неизвестная клавиша подсвечивает блок нажатия клавиш."""
    tree = block("ck_key", block_id="key-1", fields={"KEYS": "ctrl+nosuchkey"})
    with pytest.raises(BlocklyTranslationError) as excinfo:
        workspace_to_scenario(workspace(tree))

    assert excinfo.value.issues[0].block_id == "key-1"


def test_too_deep_nesting_is_error() -> None:
    """Слишком глубокая вложенность ловится до рекурсии Python."""
    inner: dict[str, Any] = click("deepest")
    for index in range(40):
        inner = block(
            "ck_loop",
            block_id=f"loop-{index}",
            fields={"TIMES": 1},
            inputs={"DO": statement(inner)},
        )

    with pytest.raises(BlocklyTranslationError) as excinfo:
        workspace_to_scenario(workspace(inner))

    assert any("вложенность" in issue.message.lower() for issue in excinfo.value.issues)
    assert any(issue.block_id is not None for issue in excinfo.value.issues)


def test_broken_workspace_container_is_error() -> None:
    """Отсутствие списка блоков — понятная ошибка без id."""
    with pytest.raises(BlocklyTranslationError) as excinfo:
        workspace_to_scenario({"blocks": {}})

    assert "нет списка блоков" in excinfo.value.issues[0].message


# --- IR → Blockly ------------------------------------------------------------


def scenario_with_all_nodes() -> Scenario:
    """Сценарий со всеми поддерживаемыми типами узлов и стабильными id."""
    return Scenario(
        name="Все узлы",
        nodes=(
            ClickNode(id="c1", x=400, y=300, button=Button.RIGHT),
            DoubleClickNode(id="d1", x=10, y=20),
            MoveNode(id="m1", x=30, y=40, duration=0.2),
            DragNode(id="g1", x=50, y=60, duration=0.7, button=Button.MIDDLE),
            ScrollNode(id="s1", amount=3),
            ScrollNode(id="s2", amount=-4, x=70, y=80),
            KeyNode(id="k1", keys="ctrl+s"),
            DelayNode(id="t1", seconds=0.5),
            LoopNode(
                id="l1",
                times=3,
                children=(
                    MoveNode(id="m2", x=600, y=300, duration=0.2),
                    ClickNode(id="c2", x=600, y=300),
                ),
            ),
            LoopNode(
                id="l2",
                times=None,
                children=(DelayNode(id="t2", seconds=1),),
            ),
        ),
    )


def test_reverse_translation_round_trip() -> None:
    """IR → Blockly → IR сохраняет структуру, поля и id."""
    scenario = scenario_with_all_nodes()
    workspace_json = scenario_to_workspace(scenario)
    restored = workspace_to_scenario(workspace_json, scenario.name).scenario

    assert restored.to_mapping() == scenario.to_mapping()


def flatten_chain(block_value: dict[str, Any]) -> list[dict[str, Any]]:
    """Развернуть цепочку `next` в список блоков."""
    result: list[dict[str, Any]] = []
    current: dict[str, Any] | None = block_value
    while current is not None:
        result.append(current)
        link = current.get("next")
        current = link.get("block") if isinstance(link, dict) else None
    return result


def test_reverse_translation_shape() -> None:
    """Обратная трансляция строит ожидаемые блоки и statement-вход."""
    workspace_json = scenario_to_workspace(scenario_with_all_nodes())
    raw_blocks = workspace_json["blocks"]["blocks"]

    assert workspace_json["blocks"]["languageVersion"] == 0
    assert len(raw_blocks) == 1

    chain_blocks = flatten_chain(raw_blocks[0])
    assert [item["type"] for item in chain_blocks] == [
        "ck_click",
        "ck_double_click",
        "ck_move",
        "ck_drag",
        "ck_scroll",
        "ck_scroll_at",
        "ck_key",
        "ck_delay",
        "ck_loop",
        "ck_loop_forever",
    ]

    loop_block = chain_blocks[8]
    assert loop_block["fields"] == {"TIMES": 3}
    assert loop_block["inputs"]["DO"]["block"]["type"] == "ck_move"

    forever = chain_blocks[9]
    assert "fields" not in forever


def test_sequence_is_flattened() -> None:
    """Узел `sequence` разворачивается в стек без отдельного блока."""
    scenario = Scenario(
        nodes=(
            SequenceNode(
                id="seq",
                children=(
                    ClickNode(id="a", x=1, y=1),
                    DelayNode(id="b", seconds=1),
                ),
            ),
            ClickNode(id="c", x=2, y=2),
        )
    )
    raw_blocks = scenario_to_workspace(scenario)["blocks"]["blocks"]

    assert len(raw_blocks) == 1
    first = raw_blocks[0]
    assert first["id"] == "a"
    assert first["next"]["block"]["id"] == "b"
    assert first["next"]["block"]["next"]["block"]["id"] == "c"

    restored = workspace_to_scenario({"blocks": {"blocks": raw_blocks}}).scenario
    assert [node.id for node in restored.nodes] == ["a", "b", "c"]


def test_missing_ids_get_unique_auto_ids() -> None:
    """Узлы без id получают уникальные автоматические id."""
    scenario = Scenario(
        nodes=(
            ClickNode(x=1, y=1),
            ClickNode(x=2, y=2),
        )
    )
    raw_blocks = scenario_to_workspace(scenario)["blocks"]["blocks"]
    first = raw_blocks[0]
    second = first["next"]["block"]

    assert first["id"] == f"{AUTO_ID_PREFIX}1"
    assert second["id"] == f"{AUTO_ID_PREFIX}2"
    assert first["id"] != second["id"]


def test_auto_ids_do_not_collide_with_existing() -> None:
    """Автоматический id не совпадает с уже занятым."""
    scenario = Scenario(
        nodes=(
            ClickNode(id=f"{AUTO_ID_PREFIX}1", x=1, y=1),
            ClickNode(x=2, y=2),
        )
    )
    raw_blocks = scenario_to_workspace(scenario)["blocks"]["blocks"]

    assert raw_blocks[0]["id"] == f"{AUTO_ID_PREFIX}1"
    assert raw_blocks[0]["next"]["block"]["id"] == f"{AUTO_ID_PREFIX}2"


def test_empty_scenario_gives_empty_workspace() -> None:
    """Из пустого сценария получается пустой холст."""
    assert scenario_to_workspace(Scenario(nodes=())) == {
        "blocks": {"languageVersion": 0, "blocks": []}
    }


def test_if_node_is_rejected() -> None:
    """Зарезервированный `if` нельзя открыть в редакторе M4."""
    scenario = Scenario(nodes=(IfNode(id="if-1", condition={"pixel": [1, 2]}),))

    with pytest.raises(BlocklyTranslationError) as excinfo:
        scenario_to_workspace(scenario)

    assert excinfo.value.issues[0].block_id == "if-1"
    assert "не поддерживается" in excinfo.value.issues[0].message
