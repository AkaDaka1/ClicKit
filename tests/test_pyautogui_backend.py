"""Тесты pyautogui-бэкенда: аварийная защита превращается в наше исключение.

Реальный ввод не выполняется: отправляющие функции pyautogui подменяются.
"""

import pytest

from core.input.backend import Button, FailsafeTriggered

pyautogui = pytest.importorskip("pyautogui")

from core.input.pyautogui_backend import PyAutoguiBackend  # noqa: E402


@pytest.fixture()
def backend() -> PyAutoguiBackend:
    """Бэкенд без реальных действий (методы подменяются в каждом тесте)."""
    return PyAutoguiBackend()


def test_click_translates_failsafe(
    monkeypatch: pytest.MonkeyPatch,
    backend: PyAutoguiBackend,
) -> None:
    """`FailSafeException` pyautogui не утекает в движок как чужой тип."""

    def raise_failsafe(*args: object, **kwargs: object) -> None:
        raise pyautogui.FailSafeException("fail-safe")

    monkeypatch.setattr(pyautogui, "click", raise_failsafe)

    with pytest.raises(FailsafeTriggered):
        backend.click(10, 20, Button.LEFT)


def test_move_translates_failsafe(
    monkeypatch: pytest.MonkeyPatch,
    backend: PyAutoguiBackend,
) -> None:
    """Защита срабатывает и на перемещении курсора."""

    def raise_failsafe(*args: object, **kwargs: object) -> None:
        raise pyautogui.FailSafeException("fail-safe")

    monkeypatch.setattr(pyautogui, "moveTo", raise_failsafe)

    with pytest.raises(FailsafeTriggered):
        backend.move_to(10, 20)


def test_position_returns_integers(backend: PyAutoguiBackend) -> None:
    """Пикер получает кортеж целых координат."""
    x, y = backend.position()
    assert isinstance(x, int)
    assert isinstance(y, int)
