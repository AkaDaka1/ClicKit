"""Узлы IR-сценария и их сериализация в JSON-совместимый словарь."""

from dataclasses import dataclass, fields
from enum import Enum
from typing import Any, ClassVar

from core.input.backend import Button

#: Версия формата сценария (увеличивается только при несовместимых изменениях).
SCENARIO_VERSION = 1


@dataclass(frozen=True, kw_only=True)
class Node:
    """Базовый узел IR. Все узлы неизменяемы и имеют необязательный `id`."""

    id: str | None = None
    type: ClassVar[str] = "node"

    def to_mapping(self) -> dict[str, Any]:
        """Словарь для JSON: `type`, `id` (если задан) и поля узла."""
        result: dict[str, Any] = {"type": self.type}
        if self.id is not None:
            result["id"] = self.id
        for field in fields(self):
            if field.name == "id":
                continue
            value = getattr(self, field.name)
            if field.name == "times" and value is None:
                # `loop.times = null` — бесконечный цикл; null нужно сохранить.
                result["times"] = None
                continue
            if value is None:
                continue
            if isinstance(value, Enum):
                value = value.value
            elif isinstance(value, tuple):
                value = [child.to_mapping() for child in value]
            result[field.name] = value
        return result


@dataclass(frozen=True, kw_only=True)
class ClickNode(Node):
    """Одиночный клик в точку экрана."""

    x: int
    y: int
    button: Button = Button.LEFT
    type: ClassVar[str] = "click"


@dataclass(frozen=True, kw_only=True)
class DoubleClickNode(Node):
    """Двойной клик в точку экрана."""

    x: int
    y: int
    button: Button = Button.LEFT
    type: ClassVar[str] = "double_click"


@dataclass(frozen=True, kw_only=True)
class MoveNode(Node):
    """Перемещение курсора в точку."""

    x: int
    y: int
    duration: float = 0.0
    type: ClassVar[str] = "move"


@dataclass(frozen=True, kw_only=True)
class DragNode(Node):
    """Перетаскивание курсора с зажатой кнопкой мыши."""

    x: int
    y: int
    duration: float = 0.5
    button: Button = Button.LEFT
    type: ClassVar[str] = "drag"


@dataclass(frozen=True, kw_only=True)
class DelayNode(Node):
    """Пауза в секундах."""

    seconds: float
    type: ClassVar[str] = "delay"


@dataclass(frozen=True, kw_only=True)
class KeyNode(Node):
    """Нажатие клавиши или комбинации (`ctrl+s`, `f5`)."""

    keys: str
    type: ClassVar[str] = "key"


@dataclass(frozen=True, kw_only=True)
class ScrollNode(Node):
    """Прокрутка колеса мыши; `x`/`y` — необязательная точка прокрутки."""

    amount: int
    x: int | None = None
    y: int | None = None
    type: ClassVar[str] = "scroll"


@dataclass(frozen=True, kw_only=True)
class LoopNode(Node):
    """Цикл: `times` повторов; `None` — до остановки."""

    times: int | None
    children: tuple[Node, ...]
    type: ClassVar[str] = "loop"


@dataclass(frozen=True, kw_only=True)
class SequenceNode(Node):
    """Группа узлов, выполняемых подряд."""

    children: tuple[Node, ...]
    type: ClassVar[str] = "sequence"


@dataclass(frozen=True, kw_only=True)
class IfNode(Node):
    """Условный узел — **резерв** формата: интерпретатор пока отказывает."""

    condition: dict[str, Any]
    then: tuple[Node, ...] = ()
    otherwise: tuple[Node, ...] = ()
    type: ClassVar[str] = "if"

    def to_mapping(self) -> dict[str, Any]:
        """Словарь для JSON: `condition`, `then` и `else` (ключ `else`)."""
        result: dict[str, Any] = {"type": self.type}
        if self.id is not None:
            result["id"] = self.id
        result["condition"] = dict(self.condition)
        result["then"] = [child.to_mapping() for child in self.then]
        result["else"] = [child.to_mapping() for child in self.otherwise]
        return result


@dataclass(frozen=True)
class Scenario:
    """Сценарий целиком: имя, версия формата и корневые узлы."""

    nodes: tuple[Node, ...]
    name: str = ""
    version: int = SCENARIO_VERSION

    def to_mapping(self) -> dict[str, Any]:
        """Словарь для JSON-файла `.acl.json`."""
        payload: dict[str, Any] = {"version": self.version}
        if self.name:
            payload["name"] = self.name
        payload["nodes"] = [node.to_mapping() for node in self.nodes]
        return payload
