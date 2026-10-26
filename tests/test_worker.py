"""Тесты общего потокового воркера."""

import threading
import time
from collections.abc import Callable

from core.input.backend import FailsafeTriggered
from core.worker import StopReason, ThreadedWorker


class StubWorker(ThreadedWorker):
    """Воркер с подменяемым телом прогона и счётчиком запусков."""

    def __init__(
        self,
        body: Callable[[threading.Event], bool],
        on_finish: Callable[[StopReason, str], None] | None = None,
    ) -> None:
        super().__init__(on_finish=on_finish)
        self._body = body
        self.starts = 0

    def _run_body(self, stop: threading.Event) -> bool:
        self.starts += 1
        return self._body(stop)


def wait_until(predicate: Callable[[], bool], timeout: float = 1.0) -> bool:
    """Ждать выполнения условия с опросом; вернуть итоговое состояние."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def make_recorder() -> tuple[
    list[tuple[StopReason, str]], Callable[[StopReason, str], None]
]:
    """Собрать список вызовов `on_finish`."""
    results: list[tuple[StopReason, str]] = []

    def on_finish(reason: StopReason, detail: str) -> None:
        results.append((reason, detail))

    return results, on_finish


def test_completed_reason() -> None:
    """Тело вернуло `True` — работа завершена."""
    results, on_finish = make_recorder()
    worker = StubWorker(lambda stop: True, on_finish=on_finish)
    worker.start()

    assert wait_until(lambda: results)
    assert results == [(StopReason.COMPLETED, "")]


def test_stopped_reason() -> None:
    """Стоп во время работы — причина STOPPED."""
    results, on_finish = make_recorder()
    worker = StubWorker(lambda stop: not stop.wait(2.0), on_finish=on_finish)
    worker.start()
    assert worker.is_running

    worker.stop()

    assert wait_until(lambda: results)
    assert results[0][0] is StopReason.STOPPED
    assert worker.join(timeout=1.0)


def test_failsafe_reason() -> None:
    """Аварийная защита бэкенда — FAILSAFE с текстом."""
    results, on_finish = make_recorder()

    def body(stop: threading.Event) -> bool:
        raise FailsafeTriggered("курсор в углу экрана")

    worker = StubWorker(body, on_finish=on_finish)
    worker.start()

    assert wait_until(lambda: results)
    assert results == [(StopReason.FAILSAFE, "курсор в углу экрана")]


def test_error_reason() -> None:
    """Любое другое исключение — ERROR с текстом."""
    results, on_finish = make_recorder()

    def body(stop: threading.Event) -> bool:
        raise RuntimeError("нет связи")

    worker = StubWorker(body, on_finish=on_finish)
    worker.start()

    assert wait_until(lambda: results)
    assert results == [(StopReason.ERROR, "нет связи")]


def test_on_finish_called_once_and_restart_works() -> None:
    """`on_finish` — один раз за прогон; после завершения можно запустить снова."""
    results, on_finish = make_recorder()
    worker = StubWorker(lambda stop: True, on_finish=on_finish)

    worker.start()
    assert wait_until(lambda: len(results) == 1)
    assert worker.join(timeout=1.0)

    worker.start()
    assert wait_until(lambda: len(results) == 2)
    assert worker.starts == 2


def test_start_while_running_is_noop() -> None:
    """Повторный `start` во время работы не создаёт второй поток."""
    release = threading.Event()
    worker = StubWorker(lambda stop: release.wait(2.0))
    worker.start()
    assert worker.is_running

    worker.start()
    assert worker.starts == 1

    release.set()
    assert wait_until(lambda: not worker.is_running)
