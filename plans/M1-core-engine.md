# M1 — Базовый движок кликов (core, без GUI)

> План согласован с пользователем (2026-10-24).
> Критерий готовности: демо-скрипт кликает в заданную точку N раз и
> мгновенно останавливается по F6 из любого приложения;
> `ruff check .` — 0 ошибок; `pytest` — зелёные.

## Параметры (согласованные)

| Параметр | Значение |
|----------|----------|
| Бэкенд отправки | только pyautogui (pynput — только глобальные слушатели, ADR №7) |
| Хоткеи | F5 — старт, F6 — аварийный стоп |
| Executor | `threading.Thread` + `threading.Event` (без Qt — `core/` не знает GUI) |
| Сценарий | плоский список команд: click / pause / move; интервал и повторы — параметры executor'а |
| Демо | `scripts/demo_click.py`, запуск из консоли |
| Тесты | mock-бэкенд, реальный ввод в тестах не выполняется |
| Настройки (`%APPDATA%`) | в M1 нет — с M2 |
| Git | ветка `feat/m1-core-engine`, 6 коммитов, затем push в master |

## Шаги

### 1. `core/input/backend.py` — ABC `InputBackend`

```python
"""Бэкенд эмуляции ввода: контракт для движка."""

from abc import ABC, abstractmethod
from enum import Enum


class Button(Enum):
    """Кнопка мыши."""

    LEFT = "left"
    RIGHT = "right"
    MIDDLE = "middle"


class InputBackend(ABC):
    """Абстрактный интерфейс эмуляции ввода (клики, движения, клавиши)."""

    @abstractmethod
    def click(self, x: int, y: int, button: Button = Button.LEFT) -> None:
        """Одиночный клик в абсолютных координатах экрана."""

    @abstractmethod
    def double_click(self, x: int, y: int, button: Button = Button.LEFT) -> None:
        """Двойной клик в абсолютных координатах экрана."""

    @abstractmethod
    def move_to(self, x: int, y: int, duration: float = 0.0) -> None:
        """Переместить курсор в точку. `duration` — секунды, 0 — мгновенно."""

    @abstractmethod
    def drag_to(self, x: int, y: int, duration: float = 0.5,
                button: Button = Button.LEFT) -> None:
        """Перетащить курсор в точку, удерживая `button`."""

    @abstractmethod
    def press_key(self, keys: str) -> None:
        """Нажать комбинацию клавиш, формат pyautogui: 'ctrl+s', 'f1', 'a'."""

    @abstractmethod
    def scroll(self, amount: int, x: int | None = None,
               y: int | None = None) -> None:
        """Колесо мыши: `amount > 0` — вверх, `amount < 0` — вниз."""
```

- Фабрика `create_backend() -> InputBackend` — в M1 всегда возвращает
  `PyAutoguiBackend` (выбор по конфигу — с M2, вместе с настройками).

### 2. `core/input/pyautogui_backend.py` — `PyAutoguiBackend`

- Отображение методов ABC на вызовы pyautogui 1:1; `press_key` дробит
  комбинацию по `+` → `pyautogui.hotkey(...)` / `pyautogui.press(...)`.
- При импорте модуля: `pyautogui.FAILSAFE = True` (курсор в угол экрана —
  аварийный стоп), `pyautogui.PAUSE = 0` (встроенные паузы pyautogui не
  искажают интервал сценария).
- Система координат: абсолютные, виртуальный рабочий экран (как в pyautogui).

### 3. `core/executor.py` — воркер

```python
"""Исполнение плоского списка команд в отдельном потоке (M1)."""


class CommandType(Enum):
    """Вид команды сценария."""

    CLICK = "click"
    PAUSE = "pause"
    MOVE = "move"


@dataclass(frozen=True)
class Command:
    """Одна команда сценария."""

    kind: CommandType
    x: int | None = None
    y: int | None = None
    button: Button = Button.LEFT
    duration: float = 0.0   # для move
    seconds: float = 0.0    # для pause


class Executor:
    """Исполняет список команд в daemon-потоке, потокобезопасный стоп."""

    def __init__(self, backend: InputBackend, commands: Sequence[Command],
                 interval: float = 0.0, repeats: int | None = None,
                 on_step: Callable[[int], None] | None = None) -> None: ...
    def start(self) -> None: ...      # no-op, если уже работает
    def stop(self) -> None: ...       # установить флаг остановки
    @property
    def is_running(self) -> bool: ...
```

- `repeats: None` — прогонять список по кругу до стопа; `repeats: N` — N проходов.
- Сон между командами — прерываемый: `self._stop.wait(interval)` — F6
  останавливает «между командами», а не после полного сна.
- `on_step(i)` вызывается в воркер-потоке — только лёгкая работа
  (счётчики, лог).
- Qt не импортируется; в M2 GUI-адаптер (QObject) обернёт executor
  и передаст статусы в сигналы.

### 4. `core/hotkeys.py` — `HotkeyManager`

```python
"""Глобальные хоткеи на основе pynput (слушатель в отдельном потоке)."""


class HotkeyManager:
    """Регистрация глобальных хоткеев и управление слушателем."""

    def register(self, spec: str, callback: Callable[[], None]) -> None: ...
    def start(self) -> None: ...      # идемпотентно
    def stop(self) -> None: ...       # идемпотентно
```

- Внутри — `pynput.keyboard.GlobalHotKeys` (ведёт свой daemon-поток).
- Callback срабатывает в потоке слушателя → только установка флагов/событий
  (в M1 — `executor.start()` / `executor.stop()`), никакой тяжёлой работы.
- Привязки M1 (в демо): `'<f5>'` → старт, `'<f6>'` → стоп.

### 5. `tests/test_executor.py` — mock-бэкенд

- `MockBackend(InputBackend)` — логирует вызовы в список.
- Тесты:
  1. Команды выполняются в заданном порядке.
  2. `repeats=2` — команды ровно 2 раза.
  3. `stop()` — executor прекращает работу после текущей команды
     (ограниченное ожидание ≤ 1 с).
  4. Интервал между командами соблюдается (приближённая проверка с допуском).
- Короткие интервалы (≤ 0.2 с), без реального ввода, без флейков.

### 6. `scripts/demo_click.py` — консольное демо

```
python scripts/demo_click.py --x 1000 --y 500 --count 100 --interval 0.1 [--button left]
```

- `commands = [Command(kind=CLICK, x=x, y=y)]`, `repeats=count`.
- Авто-старта нет: вывод «F5 — старт, F6 — стоп, Esc — выход».
- F5 — старт (no-op, если уже работает); F6 — стоп;
  после `count` кликов — вывод «готово».
- Прогресс (счётчик кликов) — в консоль через `on_step`.

### 7. Документация (после кода)

- `PROGRESS.md` — запись в журнале, «Текущий статус» (ближайшая веха → M2),
  «Следующие шаги» — M2.
- `README.md` — статус: M1 завершён (core работает, демо из консоли).
- `AI_CONTEXT.md` — дата «Последнее обновление».
- `plans/M1-core-engine.md` — отметить пункты чек-листа приёмки.
- (ADR №7 и правило `plans/` уже внесены 2026-10-24 до старта M1.)

### 8. Коммиты (ветка `feat/m1-core-engine`)

1. `feat: InputBackend ABC + pyautogui-бэкенд`
2. `feat: executor — воркер с потокобезопасным стопом`
3. `feat: глобальные хоткеи F5/F6 (pynput-слушатель)`
4. `test: юнит-тесты executor с mock-бэкендом`
5. `feat: консольный демо-скрипт`
6. `docs: M1 завершён — PROGRESS, README, AI_CONTEXT`

## Чек-лист приёмки

- [x] `ruff check .` — 0 ошибок; `pytest` — зелёные (5 passed)
- [x] Демо: 100 кликов в точку с интервалом 0.1 с
- [x] F6 из любого приложения — стоп на следующей шаге (мгновенно)
- [x] F5 — старт / перезапуск после стопа
- [x] Failsafe: курсор в угол экрана — стоп
- [x] Ветка `feat/m1-core-engine` запушена и влита в `master`
- [x] Документация: PROGRESS (журнал + статус → M2), README, дата AI_CONTEXT
- [x] `plans/M1-core-engine.md` — чек-лист приёмки отмечен

## После M1 (на будущее)

- **M2** — GUI: главное окно с двумя режимами; «Простой режим»: пикер
  (F8), кнопка мыши, интервал, повторы/∞, старт-стоп по хоткею и кнопке,
  трей-иконка.
- pynput/raw-input бэкенд отправки — только если подтвердятся конфликты
  с полноэкранными играми (PROGRESS.md, «Известные проблемы»).
