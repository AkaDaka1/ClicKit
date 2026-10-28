"""Тесты конверсии хоткеев: Qt-строка ↔ спецификация pynput и проверки."""

import pytest

from core.hotkey_spec import (
    normalize_spec,
    sequence_to_spec,
    spec_problem,
    spec_to_text,
    validate_hotkeys,
)
from core.settings import Settings


@pytest.mark.parametrize(
    ("sequence", "expected"),
    [
        ("F5", "<f5>"),
        ("F12", "<f12>"),
        ("Ctrl+Alt+S", "<ctrl>+<alt>+s"),
        ("Alt+Shift+A", "<alt>+<shift>+a"),
        ("Meta+Space", "<cmd>+<space>"),
        ("Ctrl+Shift+1", "<ctrl>+<shift>+1"),
        ("PgUp", "<page_up>"),
        ("Ctrl+Alt+Shift+Meta+S", "<ctrl>+<alt>+<shift>+<cmd>+s"),
    ],
)
def test_sequence_to_spec(sequence: str, expected: str) -> None:
    """Раскладка Qt превращается в спецификацию pynput."""
    assert sequence_to_spec(sequence) == expected


@pytest.mark.parametrize("sequence", ["", "Ctrl", "Ctrl+Shift", "НеизвестнаяКлавиша"])
def test_sequence_without_key_is_rejected(sequence: str) -> None:
    """Сочетание без клавиши или с неизвестной клавишей не принимается."""
    assert sequence_to_spec(sequence) is None


def test_normalize_orders_modifiers() -> None:
    """Модификаторы упорядочиваются: Ctrl, Alt, Shift, Win."""
    assert normalize_spec("<alt>+<ctrl>+S") == "<ctrl>+<alt>+s"
    assert (
        normalize_spec("<win>+<shift>+<alt>+<ctrl>+s") == "<ctrl>+<alt>+<shift>+<cmd>+s"
    )
    assert normalize_spec("") == ""
    assert normalize_spec("<ctrl>") == ""


def test_spec_to_text() -> None:
    """Пользователю показывается понятная запись сочетания."""
    assert spec_to_text("<f5>") == "F5"
    assert spec_to_text("<ctrl>+<alt>+s") == "Ctrl+Alt+S"
    assert spec_to_text("<cmd>+<shift>+<f6>") == "Shift+Win+F6"
    assert spec_to_text("<page_up>") == "PageUp"
    assert spec_to_text("") == ""


@pytest.mark.parametrize(
    "spec",
    ["<f5>", "<f12>", "<ctrl>+<alt>+s", "<shift>+<f6>", "<cmd>+s"],
)
def test_safe_specs_have_no_problem(spec: str) -> None:
    """Функциональные клавиши и сочетания с Ctrl/Alt/Win допустимы."""
    assert spec_problem(spec) is None


def test_empty_spec_requires_assignment() -> None:
    """Пустой хоткей не принимается: аварийный стоп обязателен."""
    assert spec_problem("") == "Назначьте сочетание клавиш"
    assert spec_problem("<ctrl>") == "Назначьте сочетание клавиш"


@pytest.mark.parametrize("spec", ["a", "1", "<esc>", "<tab>", "<shift>+a", "<space>"])
def test_bare_keys_are_rejected(spec: str) -> None:
    """Без Ctrl/Alt/Win сочетание срабатывало бы при наборе текста."""
    problem = spec_problem(spec)
    assert problem is not None
    assert "Ctrl, Alt или Win" in problem


def test_validate_default_hotkeys() -> None:
    """Хоткеи по умолчанию корректны и не конфликтуют."""
    defaults = Settings()
    assert (
        validate_hotkeys(
            {
                "start": defaults.hotkey_start,
                "stop": defaults.hotkey_stop,
                "pick": defaults.hotkey_pick,
            }
        )
        == {}
    )


def test_validate_reports_duplicates() -> None:
    """Одинаковые сочетания отклоняются с указанием поля-конфликта."""
    problems = validate_hotkeys({"start": "<f5>", "stop": "<f5>", "pick": "<f8>"})

    assert "start" in problems
    assert "stop" in problems
    assert "Старт" in problems["stop"]
    assert "Стоп" in problems["start"]


def test_validate_reports_empty_stop() -> None:
    """Пустой стоп подсвечивается отдельным полем."""
    problems = validate_hotkeys({"start": "<f5>", "stop": "", "pick": "<f8>"})

    assert set(problems) == {"stop"}
    assert problems["stop"] == "Назначьте сочетание клавиш"
