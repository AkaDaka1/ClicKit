# M0 — Инициализация структуры репозитория

> План согласован с пользователем (2026-10-23).
> Критерий готовности: `python -m app` открывает окно «ClicKit», `ruff check .` — 0 ошибок.

## Параметры (согласованные)

| Параметр | Значение |
|----------|----------|
| Длина строки (ruff) | 88 |
| `target-version` | `py311` |
| `__init__.py` | пустые файлы (без docstring) |
| `MainWindow` в M0 | минимальное окно (заголовок + размер) |
| Версии зависимостей | мягкие (`>=`) |
| `QtWebEngine` | не нужен до M4 |

## Шаги

### 1. Структура каталогов

```
app/
├── __init__.py
├── __main__.py
└── application.py

core/
├── __init__.py
├── input/
│   └── __init__.py
├── ir/
│   └── __init__.py
├── executor.py          # заглушка → M1
├── hotkeys.py           # заглушка → M1
└── recorder.py          # заглушка → M3

gui/
├── __init__.py
├── main_window.py
├── simple_mode/
│   └── __init__.py
├── editor/
│   └── __init__.py
└── widgets/
    └── __init__.py

bridge/
└── __init__.py

resources/
├── blockly/
├── icons/
└── styles/

tests/
└── __init__.py
```

### 2. requirements.txt

```
# Runtime
PySide6>=6.7
pyautogui>=0.9
pynput>=1.7

# Dev
ruff>=0.8
pytest>=8.0
```

### 3. pyproject.toml — ruff

```toml
[project]
name = "clickit"
version = "0.1.0"
requires-python = ">=3.11"

[tool.ruff]
target-version = "py311"
line-length = 88

[tool.ruff.lint]
select = ["E", "F", "W", "I", "UP", "B"]
ignore = []

[tool.ruff.lint.isort]
known-first-party = ["app", "core", "gui", "bridge"]
```

### 4. Точка входа

**`app/__main__.py`:**
```python
"""Точка входа ClicKit: python -m app."""

import sys

from PySide6.QtWidgets import QApplication

from gui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("ClicKit")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
```

**`app/application.py`:**
```python
"""Сборка QApplication и главного окна."""

import sys

from PySide6.QtWidgets import QApplication

from gui.main_window import MainWindow


def run() -> int:
    """Точка входа: создать приложение, окно, запустить event loop."""
    app = QApplication(sys.argv)
    app.setApplicationName("ClicKit")
    window = MainWindow()
    window.show()
    return app.exec()
```

**`gui/main_window.py`:**
```python
"""Главное окно ClicKit."""

from PySide6.QtWidgets import QMainWindow


class MainWindow(QMainWindow):
    """Главное окно приложения (M0: пустое)."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("ClicKit")
        self.resize(1024, 680)
```

> Примечание: `app/__main__.py` и `app/application.py` делают почти одно и то же.
> `__main__.py` — тонкий wrapper, `application.py` — место для будущей DI-сборки.
> Пока дублируем, чтобы не усложнять; в M2 упростим.

### 5. Обновление документации

- `AGENTS.md` — заполнить секцию «Команды»:
  ```
  - Установка зависимостей: `pip install -r requirements.txt`
  - Запуск: `python -m app`
  - Проверки: `ruff check .` + `pytest`
  ```
- `PROGRESS.md` — запись в журнале о M0
- `AI_CONTEXT.md` — обновить дату в подвале

### 6. Коммит

```
feat: initialize project skeleton with entry point (M0)
```

## После M0 (на будущее)

- **M1** — `InputBackend` (pyautogui), `hotkeys.py` (F6), `executor.py`, демо
- **M2** — GUI: простое окно автокликера, пикер, трей-иконка
- **GitHub** — remote, push (после M0 или M1)
