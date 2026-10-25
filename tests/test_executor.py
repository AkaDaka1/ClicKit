"""Тесты исполнителя с mock-бэкендом (реальный ввод не выполняется)."""

import time
from collections.abc import Callable

from core.executor import Command, CommandType, Executor, StopReason
from core.input.backend import Button, FailsafeTriggered, InputBackend


class MockBackend(InputBackend):
    """Бэкенд, который только записывает вызовы в список."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []
        self.timestamps: list[float] = []

    def _record(self, name: str, *args: object) -> None:
        self.calls.append((name, args))
        self.timestamps.append(time.monotonic())

    def position(self) -> tuple[int, int]:
        """Позиция курсора — фиксированная (пикер в тестах не нужен)."""
        return (7, 9)

    def click(self, x: int, y: int, button: Button = Button.LEFT) -> None:
        self._record("click", x, y, button)

    def double_click(self, x: int, y: int, button: Button = Button.LEFT) -> None:
        self._record("double_click", x, y, button)

    def move_to(self, x: int, y: int, duration: float = 0.0) -> None:
        self._record("move_to", x, y, duration)

    def drag_to(
        self,
        x: int,
        y: int,
        duration: float = 0.5,
        button: Button = Button.LEFT,
    ) -> None:
        self._record("drag_to", x, y, duration, button)

    def press_key(self, keys: str) -> None:
        self._record("press_key", keys)

    def scroll(
        self,
        amount: int,
        x: int | None = None,
        y: int | None = None,
    ) -> None:
        self._record("scroll", amount, x, y)


def wait_until(predicate: Callable[[], bool], timeout: float = 1.0) -> bool:
    """Ждать выполнения условия с опросом; вернуть итоговое состояние."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def test_commands_executed_in_order() -> None:
    """Команды выполняются в заданном порядке."""
    backend = MockBackend()
    commands = [
        Command(CommandType.MOVE, x=10, y=20, duration=0.0),
        Command(CommandType.CLICK, x=10, y=20),
        Command(CommandType.PAUSE, seconds=0.01),
    ]
    executor = Executor(backend, commands, repeats=1)
    executor.start()
    assert wait_until(lambda: not executor.is_running, timeout=0.5)
    assert [name for name, _ in backend.calls] == ["move_to", "click"]


def test_repeats_limit_passes() -> None:
    """`repeats=2` — команды выполняются ровно 2 раза."""
    backend = MockBackend()
    commands = [Command(CommandType.CLICK, x=5, y=5)]
    executor = Executor(backend, commands, repeats=2)
    executor.start()

    assert wait_until(lambda: len(backend.calls) == 2)
    time.sleep(0.05)
    assert len(backend.calls) == 2
    assert not executor.is_running


def test_stop_interrupts_work() -> None:
    """`stop()` прекращает исполнение, не дожидаясь конца паузы."""
    backend = MockBackend()
    commands = [
        Command(CommandType.CLICK, x=1, y=2, button=Button.RIGHT),
        Command(CommandType.PAUSE, seconds=0.5),
    ]
    executor = Executor(backend, commands)
    executor.start()

    assert wait_until(lambda: len(backend.calls) == 1)
    executor.stop()

    assert wait_until(lambda: not executor.is_running, timeout=0.5)
    assert len(backend.calls) == 1
    assert backend.calls[0] == ("click", (1, 2, Button.RIGHT))


def test_interval_is_respected() -> None:
    """Интервал между командами соблюдается (приближённая проверка)."""
    backend = MockBackend()
    commands = [Command(CommandType.CLICK, x=0, y=0)]
    executor = Executor(backend, commands, interval=0.1, repeats=3)
    executor.start()

    assert wait_until(lambda: len(backend.calls) == 3)
    gaps = [
        later - earlier
        for earlier, later in zip(
            backend.timestamps,
            backend.timestamps[1:],
            strict=False,
        )
    ]
    assert len(gaps) == 2
    assert all(gap >= 0.09 for gap in gaps)


def test_empty_commands_finish_immediately() -> None:
    """Пустой список команд не запускает бесконечный цикл."""
    executor = Executor(MockBackend(), [])
    executor.start()

    assert wait_until(lambda: not executor.is_running, timeout=0.5)


class FailsafeBackend(MockBackend):
    """Бэкенд, у которого клик попадает в аварийную защиту."""

    def click(self, x: int, y: int, button: Button = Button.LEFT) -> None:
        raise FailsafeTriggered("курсор в углу экрана")


class BrokenBackend(MockBackend):
    """Бэкенд, который падает с обычной ошибкой."""

    def click(self, x: int, y: int, button: Button = Button.LEFT) -> None:
        raise RuntimeError("бэкенд недоступен")


def make_finish_recorder() -> tuple[
    list[tuple[StopReason, str]], Callable[[StopReason, str], None]
]:
    """Собрать список для проверки вызовов `on_finish`."""
    results: list[tuple[StopReason, str]] = []

    def on_finish(reason: StopReason, detail: str) -> None:
        results.append((reason, detail))

    return results, on_finish


def test_finish_completed() -> None:
    """Все повторы выполнены — причина COMPLETED, подробности пустые."""
    results, on_finish = make_finish_recorder()
    executor = Executor(
        MockBackend(),
        [Command(CommandType.CLICK, x=3, y=4)],
        repeats=2,
        on_finish=on_finish,
    )
    executor.start()

    assert wait_until(lambda: results, timeout=1.0)
    assert results == [(StopReason.COMPLETED, "")]


def test_finish_stopped() -> None:
    """Остановка по флагу — причина STOPPED."""
    results, on_finish = make_finish_recorder()
    backend = MockBackend()
    executor = Executor(
        backend,
        [
            Command(CommandType.CLICK, x=1, y=1),
            Command(CommandType.PAUSE, seconds=1.0),
        ],
        on_finish=on_finish,
    )
    executor.start()
    assert wait_until(lambda: len(backend.calls) == 1)
    executor.stop()

    assert wait_until(lambda: results, timeout=1.0)
    assert results[0][0] is StopReason.STOPPED


def test_finish_failsafe() -> None:
    """Аварийная защита бэкенда — причина FAILSAFE и текст исключения."""
    results, on_finish = make_finish_recorder()
    executor = Executor(
        FailsafeBackend(),
        [Command(CommandType.CLICK, x=0, y=0)],
        on_finish=on_finish,
    )
    executor.start()

    assert wait_until(lambda: results, timeout=1.0)
    assert results == [(StopReason.FAILSAFE, "курсор в углу экрана")]


def test_finish_error() -> None:
    """Обычное исключение бэкенда — причина ERROR с текстом."""
    results, on_finish = make_finish_recorder()
    executor = Executor(
        BrokenBackend(),
        [Command(CommandType.CLICK, x=0, y=0)],
        on_finish=on_finish,
    )
    executor.start()

    assert wait_until(lambda: results, timeout=1.0)
    assert results == [(StopReason.ERROR, "бэкенд недоступен")]


def test_finish_called_once() -> None:
    """`on_finish` вызывается ровно один раз на прогон."""
    results, on_finish = make_finish_recorder()
    executor = Executor(
        MockBackend(),
        [Command(CommandType.CLICK, x=0, y=0)],
        repeats=1,
        on_finish=on_finish,
    )
    executor.start()

    assert wait_until(lambda: results, timeout=1.0)
    time.sleep(0.05)
    assert len(results) == 1
