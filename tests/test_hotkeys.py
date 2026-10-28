"""Тесты менеджера глобальных хоткеев: регистрация, перезагрузка, защита."""

from collections.abc import Callable

import pytest

from core import hotkeys


class FakeListener:
    """Подмена `pynput.keyboard.GlobalHotKeys` без системного слушателя."""

    instances: list["FakeListener"] = []

    def __init__(self, bindings: dict[str, Callable[[], None]]) -> None:
        self.bindings = bindings
        self.started = False
        self.stopped = False
        FakeListener.instances.append(self)

    def start(self) -> None:
        """Отметить запуск слушателя."""
        self.started = True

    def stop(self) -> None:
        """Отметить остановку слушателя."""
        self.stopped = True


@pytest.fixture(autouse=True)
def fake_listener(monkeypatch: pytest.MonkeyPatch) -> type[FakeListener]:
    """Все тесты работают на подменённом слушателе."""
    FakeListener.instances = []
    monkeypatch.setattr(hotkeys.keyboard, "GlobalHotKeys", FakeListener)
    return FakeListener


def test_register_after_start_is_rejected() -> None:
    """Регистрация после старта невозможна — привязки фиксируются снимком."""
    manager = hotkeys.HotkeyManager()
    manager.register("<f5>", lambda: None)
    manager.start()

    with pytest.raises(RuntimeError):
        manager.register("<f6>", lambda: None)


def test_reload_restarts_running_listener() -> None:
    """reload останавливает старый слушатель и запускает новый набор."""
    manager = hotkeys.HotkeyManager()
    manager.register("<f5>", lambda: None)
    manager.start()
    first = FakeListener.instances[-1]

    manager.reload({"<ctrl>+<alt>+s": lambda: None, "<f8>": lambda: None})

    second = FakeListener.instances[-1]
    assert first.stopped
    assert second.started
    assert set(second.bindings) == {"<ctrl>+<alt>+s", "<f8>"}


def test_reload_before_start_only_replaces_bindings() -> None:
    """До старта reload не создаёт слушатель, но новые привязки применяются."""
    manager = hotkeys.HotkeyManager()
    manager.reload({"<f6>": lambda: None})
    assert FakeListener.instances == []

    manager.start()

    assert set(FakeListener.instances[-1].bindings) == {"<f6>"}


def test_stop_is_idempotent() -> None:
    """Повторный stop безопасен."""
    manager = hotkeys.HotkeyManager()
    manager.stop()
    manager.register("<f6>", lambda: None)
    manager.start()
    manager.stop()
    manager.stop()

    assert FakeListener.instances[-1].stopped


def test_callback_errors_do_not_break_listener() -> None:
    """Исключение в обработчике хоткея не роняет слушатель."""
    manager = hotkeys.HotkeyManager()
    called: list[str] = []

    def failing() -> None:
        raise RuntimeError("бум")

    manager.register("<f5>", failing)
    manager.register("<f6>", lambda: called.append("ok"))
    manager.start()
    wrapped = FakeListener.instances[-1].bindings["<f5>"]
    wrapped()

    assert called == []
    FakeListener.instances[-1].bindings["<f6>"]()
    assert called == ["ok"]
