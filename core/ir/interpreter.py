"""Интерпретатор IR-сценария: обход узлов и вызовы `InputBackend`."""

import threading
from collections.abc import Callable

from core.input.backend import FailsafeTriggered, InputBackend
from core.ir.nodes import (
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


class ScenarioRuntimeError(RuntimeError):
    """Сценарий не удалось выполнить; `path` — узел, на котором произошла ошибка."""

    def __init__(self, message: str, path: str) -> None:
        """Запомнить путь узла и собрать текст с указанием места."""
        self.path = path
        super().__init__(f"{message} (узел {path})")


class Interpreter:
    """Выполняет сценарий последовательно, с поддержкой остановки.

    Интерпретатор не создаёт поток: его запускает `ScenarioRunner` (или
    консольный скрипт). Остановка проверяется перед каждым узлом и каждой
    итерацией цикла, паузы прерываются немедленно.
    """

    def __init__(
        self,
        backend: InputBackend,
        scenario: Scenario,
        stop_event: threading.Event | None = None,
        on_step: Callable[[int], None] | None = None,
        on_node: Callable[[Node, str], None] | None = None,
        dry_run: bool = False,
    ) -> None:
        """Создать интерпретатор.

        Args:
            backend: бэкенд эмуляции ввода.
            scenario: проверенный сценарий.
            stop_event: общий флаг остановки; `None` — создать свой.
            on_step: callback после каждого действия (счётчик с 1);
                вызывается в потоке исполнения.
            on_node: callback перед выполнением узла (узел и его путь);
                нужен GUI для подсветки текущего блока.
            dry_run: не выполнять ввод и не ждать паузы — только проверить
                план (бесконечный цикл проходится один раз).
        """
        self._backend = backend
        self._scenario = scenario
        self._stop = stop_event if stop_event is not None else threading.Event()
        self._on_step = on_step
        self._on_node = on_node
        self._dry_run = dry_run
        self._steps = 0

    @property
    def steps(self) -> int:
        """Сколько действий выполнено в текущем/последнем прогоне."""
        return self._steps

    def stop(self) -> None:
        """Запросить остановку: исполнение прервётся на ближайшей проверке."""
        self._stop.set()

    def run(self) -> int:
        """Выполнить сценарий целиком (или до остановки); вернуть число действий."""
        self._steps = 0
        self._run_nodes(self._scenario.nodes, "nodes")
        return self._steps

    def _run_nodes(self, nodes: tuple[Node, ...], path: str) -> bool:
        """Выполнить список узлов. `False` — прервано остановкой."""
        for index, node in enumerate(nodes):
            if self._stop.is_set():
                return False
            if not self._run_node(node, f"{path}[{index}]"):
                return False
        return True

    def _run_node(self, node: Node, path: str) -> bool:
        """Выполнить один узел. `False` — прервано остановкой."""
        self._notify_node(node, path)

        if isinstance(node, ClickNode):
            self._call(path, self._backend.click, node.x, node.y, node.button)
        elif isinstance(node, DoubleClickNode):
            self._call(path, self._backend.double_click, node.x, node.y, node.button)
        elif isinstance(node, MoveNode):
            self._call(path, self._backend.move_to, node.x, node.y, node.duration)
        elif isinstance(node, DragNode):
            self._call(
                path,
                self._backend.drag_to,
                node.x,
                node.y,
                node.duration,
                node.button,
            )
        elif isinstance(node, DelayNode):
            if not self._dry_run and self._stop.wait(node.seconds):
                return False
        elif isinstance(node, KeyNode):
            self._call(path, self._backend.press_key, node.keys)
        elif isinstance(node, ScrollNode):
            self._call(path, self._backend.scroll, node.amount, node.x, node.y)
        elif isinstance(node, LoopNode):
            return self._run_loop(node, path)
        elif isinstance(node, SequenceNode):
            return self._run_nodes(node.children, f"{path}.children")
        elif isinstance(node, IfNode):
            raise ScenarioRuntimeError(
                "Узел 'if' пока не поддерживается: условия появятся "
                "в следующих версиях",
                path,
            )
        else:  # pragma: no cover — защита от новых типов узлов
            raise ScenarioRuntimeError(
                f"Неизвестный узел: {type(node).__name__}",
                path,
            )

        self._advance()
        return True

    def _run_loop(self, node: LoopNode, path: str) -> bool:
        """Выполнять тело цикла `times` раз или до остановки при `None`."""
        children_path = f"{path}.children"
        times = node.times
        if self._dry_run and times is None:
            times = 1
        iteration = 0
        while times is None or iteration < times:
            if self._stop.is_set():
                return False
            if iteration > 0:
                # Подсветка блока цикла на каждой итерации (M4).
                self._notify_node(node, path)
            if not self._run_nodes(node.children, children_path):
                return False
            iteration += 1
        return True

    def _call(self, path: str, func: Callable[..., None], *args: object) -> None:
        """Вызвать метод бэкенда, добавив путь узла к ошибке."""
        if self._dry_run:
            return
        try:
            func(*args)
        except FailsafeTriggered:
            # Аварийная защита должна дойти до воркера без изменений.
            raise
        except ScenarioRuntimeError:
            raise
        except Exception as exc:  # noqa: BLE001 — контекст важнее типа
            raise ScenarioRuntimeError(
                f"Ошибка выполнения: {exc or type(exc).__name__}",
                path,
            ) from exc

    def _advance(self) -> None:
        """Учесть выполненное действие и уведомить наблюдателя."""
        self._steps += 1
        if self._on_step is not None:
            self._on_step(self._steps)

    def _notify_node(self, node: Node, path: str) -> None:
        """Сообщить о начале выполнения узла (для подсветки в GUI)."""
        if self._on_node is not None:
            self._on_node(node, path)
