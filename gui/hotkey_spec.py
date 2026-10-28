"""Хоткеи: спецификация pynput ↔ человекочитаемый текст (без виджетов).

В настройках и ядре хоткей хранится в формате pynput (`<ctrl>+<alt>+s`),
в интерфейсе показывается как `Ctrl+Alt+S`. Все преобразования — чистые
функции, поэтому их удобно тестировать без Qt.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

#: Порядок модификаторов в нормализованной спецификации.
MODIFIER_ORDER: tuple[str, ...] = ("ctrl", "alt", "shift", "cmd")

#: Псевдонимы модификаторов → каноническое имя в pynput.
MODIFIER_ALIASES: dict[str, str] = {
    "ctrl": "ctrl",
    "control": "ctrl",
    "alt": "alt",
    "shift": "shift",
    "cmd": "cmd",
    "meta": "cmd",
    "win": "cmd",
    "windows": "cmd",
    "super": "cmd",
}

#: Человекочитаемые подписи модификаторов.
MODIFIER_LABELS: dict[str, str] = {
    "ctrl": "Ctrl",
    "alt": "Alt",
    "shift": "Shift",
    "cmd": "Win",
}

#: Имена клавиш Qt (`PortableText`) → имена pynput.
NAMED_KEYS: dict[str, str] = {
    "space": "space",
    "tab": "tab",
    "backtab": "tab",
    "enter": "enter",
    "return": "enter",
    "esc": "esc",
    "escape": "esc",
    "backspace": "backspace",
    "delete": "delete",
    "del": "delete",
    "insert": "insert",
    "ins": "insert",
    "home": "home",
    "end": "end",
    "pageup": "page_up",
    "pgup": "page_up",
    "pagedown": "page_down",
    "pgdown": "page_down",
    "up": "up",
    "down": "down",
    "left": "left",
    "right": "right",
    "print": "print_screen",
    "printscreen": "print_screen",
    "pause": "pause",
    "capslock": "caps_lock",
    "numlock": "num_lock",
    "scrolllock": "scroll_lock",
}

#: Обратные подписи для показа пользователю (pynput → текст).
KEY_LABELS: dict[str, str] = {
    "space": "Space",
    "tab": "Tab",
    "enter": "Enter",
    "esc": "Esc",
    "backspace": "Backspace",
    "delete": "Delete",
    "insert": "Insert",
    "home": "Home",
    "end": "End",
    "page_up": "PageUp",
    "page_down": "PageDown",
    "up": "↑",
    "down": "↓",
    "left": "←",
    "right": "→",
    "print_screen": "PrintScreen",
    "pause": "Pause",
    "caps_lock": "CapsLock",
    "num_lock": "NumLock",
    "scroll_lock": "ScrollLock",
}

#: Подписи полей хоткеев в диалоге настроек.
FIELD_LABELS: dict[str, str] = {
    "start": "Старт",
    "stop": "Стоп",
    "pick": "Захват точки",
}

_FUNCTION_KEY = re.compile(r"^f(?:[1-9]|1[0-9]|2[0-4])$")

#: Клавиши, которые нельзя назначать без модификатора.
_BARE_FORBIDDEN = {"esc", "tab", "enter", "space", "backspace", "delete"}


def _split_tokens(text: str) -> list[str]:
    """Разбить спецификацию по `+`, корректно обрабатывая клавишу `+`."""
    stripped = text.strip()
    if not stripped:
        return []
    if stripped.endswith("++"):
        tokens = stripped[:-2].split("+") if stripped[:-2] else []
        return [token for token in tokens if token] + ["+"]
    return [token for token in stripped.split("+") if token]


def _clean_token(token: str) -> str:
    """Убрать угловые скобки и привести токен к нижнему регистру."""
    return token.strip().strip("<>").strip().lower()


def _key_spec(name: str) -> str | None:
    """Имя клавиши pynput → токен спецификации (`f5` → `<f5>`)."""
    if name in MODIFIER_ALIASES:
        return None
    if len(name) == 1:
        return None if name == "+" else name
    if _FUNCTION_KEY.match(name):
        return f"<{name}>"
    if name in NAMED_KEYS:
        return f"<{NAMED_KEYS[name]}>"
    if name in KEY_LABELS:
        return f"<{name}>"
    return None


def sequence_to_spec(sequence: str) -> str | None:
    """Преобразовать строку Qt (`Ctrl+Alt+S`) в спецификацию pynput.

    Returns:
        Нормализованная спецификация или `None`, если сочетание
        не содержит клавиши (только модификаторы) либо не распознано.
    """
    modifiers: set[str] = set()
    main: str | None = None
    for token in _split_tokens(sequence):
        lowered = _clean_token(token)
        if not lowered:
            continue
        modifier = MODIFIER_ALIASES.get(lowered)
        if modifier is not None:
            modifiers.add(modifier)
            continue
        main = _key_spec(lowered)
        if main is None:
            return None
    if main is None:
        return None
    parts = [f"<{name}>" for name in MODIFIER_ORDER if name in modifiers]
    parts.append(main)
    return "+".join(parts)


def normalize_spec(spec: str) -> str:
    """Привести спецификацию pynput к каноническому виду.

    Модификаторы идут в порядке Ctrl, Alt, Shift, Win; неизвестные
    токены отбрасываются. Пустая строка означает «не назначено».
    """
    modifiers: set[str] = set()
    main: str | None = None
    for token in _split_tokens(spec):
        lowered = _clean_token(token)
        if not lowered:
            continue
        modifier = MODIFIER_ALIASES.get(lowered)
        if modifier is not None:
            modifiers.add(modifier)
            continue
        key = _key_spec(lowered)
        if key is not None:
            main = key
    if main is None:
        return ""
    parts = [f"<{name}>" for name in MODIFIER_ORDER if name in modifiers]
    parts.append(main)
    return "+".join(parts)


def _parts(spec: str) -> tuple[set[str], str | None]:
    """Разобрать нормализованную спецификацию на модификаторы и клавишу."""
    modifiers: set[str] = set()
    main: str | None = None
    for token in _split_tokens(spec):
        lowered = _clean_token(token)
        if lowered in MODIFIER_ALIASES:
            modifiers.add(MODIFIER_ALIASES[lowered])
        elif lowered:
            main = lowered
    return modifiers, main


def spec_to_text(spec: str) -> str:
    """Показать спецификацию пользователю (`<ctrl>+<alt>+s` → `Ctrl+Alt+S`)."""
    modifiers, main = _parts(normalize_spec(spec))
    if main is None:
        return ""
    parts = [MODIFIER_LABELS[name] for name in MODIFIER_ORDER if name in modifiers]
    if len(main) == 1:
        parts.append(main.upper())
    else:
        parts.append(KEY_LABELS.get(main, main.replace("_", " ").title()))
    return "+".join(parts)


def spec_problem(spec: str) -> str | None:
    """Проверить сочетание; вернуть понятную ошибку или `None`.

    Глобальный хоткей без Ctrl/Alt/Win срабатывает при обычном наборе
    текста, поэтому такие сочетания (кроме функциональных клавиш)
    запрещены.
    """
    normalized = normalize_spec(spec)
    if not normalized:
        return "Назначьте сочетание клавиш"
    modifiers, main = _parts(normalized)
    if main is None:
        return "Добавьте клавишу к модификатору"
    if main == "+":
        return "Клавишу «+» нельзя использовать как хоткей"
    if not (_FUNCTION_KEY.match(main) or modifiers & {"ctrl", "alt", "cmd"}):
        if main in _BARE_FORBIDDEN:
            return "Добавьте Ctrl, Alt или Win — иначе клавиша перестанет работать"
        return (
            "Добавьте Ctrl, Alt или Win — иначе сочетание сработает при наборе текста"
        )
    return None


def validate_hotkeys(specs: Mapping[str, str]) -> dict[str, str]:
    """Проверить набор хоткеев: ошибки и конфликты по полям.

    Args:
        specs: поле (`start`/`stop`/`pick`) → спецификация pynput.

    Returns:
        Поле → сообщение об ошибке; пустой словарь — всё корректно.
    """
    problems: dict[str, str] = {}
    seen: dict[str, str] = {}
    for field, label in FIELD_LABELS.items():
        if field not in specs:
            continue
        spec = specs[field]
        problem = spec_problem(spec)
        if problem is not None:
            problems[field] = problem
            continue
        normalized = normalize_spec(spec)
        if normalized in seen:
            other = FIELD_LABELS[seen[normalized]]
            problems[field] = f"Сочетание уже используется для «{other}»"
            problems.setdefault(
                seen[normalized],
                f"Сочетание уже используется для «{label}»",
            )
            continue
        seen[normalized] = field
    return problems
