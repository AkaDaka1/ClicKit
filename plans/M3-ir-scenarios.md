# M3 — Модель сценариев (IR) и её исполнение

> План согласован с пользователем (2026-10-26).
> Критерий готовности (ROADMAP): сценарий «клик → пауза → цикл 10×(движение+клик)»
> исполняется из JSON без Blockly; `ruff check .` — 0 ошибок,
> `ruff format --check .` — чисто, `pytest` — зелёные.

## Параметры (согласованные)

| Параметр | Значение |
|----------|----------|
| Объём UI | **только core + консольное демо**; вся GUI-работа — в M4 (Blockly) |
| Узел `if` | **отложен** до M4/M5: тип зарезервирован в схеме, интерпретатор выдаёт понятную ошибку «не поддерживается» |
| Набор узлов | расширенный по возможностям бэкенда: `click`, `double_click`, `move`, `drag`, `delay`, `key`, `scroll`, `loop`, `sequence` (+ резерв `if`) |
| Цикл | `repeat N` и `repeat ∞` (`times: null`); `while` появится вместе с условиями |
| Recorder | **отложен** (запись мыши — после M4/M5) |
| Формат файлов | `.acl.json`, UTF-8, `version: 1`, атомарная запись |
| Git | ветка `feat/m3-ir-scenarios`, коммиты по шагам, затем merge в `master` |

## Архитектурные решения (ADR)

13. **Общий потоковый воркер** (`core/worker.py::ThreadedWorker`): запуск/стоп/join/
    причина завершения (`StopReason`) живут в одном месте. `Executor` (простой режим)
    и новый `ScenarioRunner` (IR) наследуют воркер и реализуют только тело прогона.
    Публичный API `Executor` не меняется; `StopReason` реэкспортируется из
    `core/executor.py`, чтобы существующие импорты GUI не ломались.
14. **README-формат IR, а не код** (развитие ADR №3): сценарий — это JSON
    `{"version": 1, "name": ..., "nodes": [...]}`. Узлы типизированы, все поля
    валидируются до исполнения, неизвестный `type` — ошибка. Неизвестные
    *ключи* игнорируются (задел на совместимость вперёд), неизвестная *версия* —
    ошибка с понятным текстом. Версия формата увеличивается только при
    несовместимых изменениях.
15. **Ошибки валидации — список с путями.** `ScenarioValidationError` содержит
    `issues: list[ValidationIssue(path, message)]` (путь вида
    `nodes[2].children[0].x`, до 50 ошибок за раз). Это даёт CLI понятный
    вывод, а M4 — возможность подсветить конкретный блок.
16. **Стабильные `id` узлов.** Любой узел может иметь необязательное поле
    `id` (строка, уникальная в сценарии). IR сохраняет его при загрузке/
    сохранении; интерпретатор сообщает текущий узел через `on_node(node, path)`
    — в M4 это станет подсветкой выполняемого блока без изменения формата.
17. **Проверка остановки внутри интерпретатора.** `delay` реализуется через
    `threading.Event.wait(seconds)` и прерывается стопом мгновенно; проверки
    стопа стоят перед каждым узлом и каждой итерацией цикла. Fail-safe
    (`FailsafeTriggered`) проходит наружу без обёртки и превращается
    в `StopReason.FAILSAFE` общим воркером.

## Формат `.acl.json`

```json
{
  "version": 1,
  "name": "Клик → пауза → цикл",
  "nodes": [
    {"type": "click", "x": 400, "y": 300},
    {"type": "delay", "seconds": 0.5},
    {"type": "loop", "times": 10, "children": [
      {"type": "move", "x": 600, "y": 300, "duration": 0.2},
      {"type": "click", "x": 600, "y": 300}
    ]}
  ]
}
```

### Узлы версии 1

| `type` | Поля | Ограничения |
|--------|------|-------------|
| `click` | `x`, `y` (int), `button` (`left`/`right`/`middle`, по умолч. `left`) | координаты −32 768…32 767 |
| `double_click` | как `click` | — |
| `move` | `x`, `y`, `duration` (сек, по умолч. 0) | `duration` 0…60 |
| `drag` | `x`, `y`, `duration` (по умолч. 0.5), `button` | `duration` 0…60 |
| `delay` | `seconds` (обязательно) | 0…3 600 |
| `key` | `keys` (строка, например `ctrl+s`, `f1`) | непустая, ≤ 64 символов, известные клавиши/комбинации |
| `scroll` | `amount` (int), `x`, `y` (необязательны) | `amount` −100…100, координаты в общем диапазоне |
| `loop` | `times` (int или `null` — ∞), `children` | `times` 1…1 000 000, детей ≥ 1 |
| `sequence` | `children` | детей ≥ 1 |
| `if` | `condition` (объект), `then`, `else` (списки) | **резерв**: разбирается, но интерпретатор отказывает |

Общие лимиты: глубина вложенности ≤ 32, всего узлов ≤ 10 000,
`name` ≤ 200 символов, `id` ≤ 64 символов и уникален.

## Шаги

### 1. `core/worker.py` — общий потоковый воркер

```python
class StopReason(Enum):
    COMPLETED = "completed"
    STOPPED = "stopped"
    FAILSAFE = "failsafe"
    ERROR = "error"


class ThreadedWorker(ABC):
    def __init__(
        self, on_finish: Callable[[StopReason, str], None] | None = None
    ) -> None: ...
    @property
    def is_running(self) -> bool: ...
    def start(self) -> None: ...  # no-op, если уже работает
    def stop(self) -> None: ...
    def join(self, timeout: float | None = None) -> bool: ...
    @abstractmethod
    def _run_body(self, stop: threading.Event) -> bool:
        """Выполнить работу; `False` — прогон прерван стопом."""
```

- `_run()` в базовом классе: ловит `FailsafeTriggered` → `FAILSAFE`, прочие
  исключения → `ERROR`, выставляет `STOPPED`, если стоп запрошен/`_run_body`
  вернул `False`, иначе `COMPLETED`; `on_finish` — ровно один раз.
- `core/executor.py` переписывается на наследование; `StopReason`
  импортируется из `core.worker` и реэкспортируется (публичный API и тесты M1–M2
  не меняются).

### 2. `core/ir/nodes.py` + `core/ir/schema.py` — узлы, (де)сериализация, валидация

`core/ir/nodes.py` — dataclass'ы узлов и сценария (файл держим до ~300 строк),
`schema.py` — разбор JSON и проверка полей. Публичный API — из `schema.py`.

```python
SCENARIO_VERSION = 1
MAX_NODES = 10_000
MAX_DEPTH = 32
MAX_ISSUES = 50


class Node: ...  # базовый dataclass: id: str | None = None


class ClickNode(Node): ...  # x, y, button; double: bool? — нет, отдельный класс


class DoubleClickNode(Node): ...


class MoveNode(Node): ...


class DragNode(Node): ...


class DelayNode(Node): ...


class KeyNode(Node): ...


class ScrollNode(Node): ...


class LoopNode(Node): ...  # times: int | None, children: tuple[Node, ...]


class SequenceNode(Node): ...


class IfNode(Node): ...  # зарезервирован, интерпретатор откажет


@dataclass(frozen=True)
class Scenario:
    nodes: tuple[Node, ...]
    name: str = ""
    version: int = SCENARIO_VERSION

    def to_mapping(self) -> dict[str, Any]: ...


@dataclass(frozen=True)
class ValidationIssue:
    path: str
    message: str


class ScenarioValidationError(ValueError):
    issues: tuple[ValidationIssue, ...]


def scenario_from_mapping(
    data: Any,
) -> Scenario: ...  # собирает все ошибки, потом бросает
def scenario_from_json(
    text: str,
) -> Scenario: ...  # JSONDecodeError → ValidationIssue("$", ...)
```

- Сбор ошибок: парсер идёт по дереву, копит `ValidationIssue` с путями,
  битые узлы пропускает; после обхода, если ошибки есть — исключение.
- `to_mapping()` восстанавливает поля узла без `None` (`id` — только если был);
  `loop.times = null` сохраняется явно, чтобы бесконечный цикл не потерялся.
  JSON получается читаемым и стабильным при повторном сохранении.

### 3. `core/ir/interpreter.py` — обход IR

```python
class ScenarioRuntimeError(RuntimeError):
    path: str  # где именно упало/не поддерживается


class Interpreter:
    def __init__(
        self,
        backend: InputBackend,
        scenario: Scenario,
        stop_event: threading.Event | None = None,
        on_step: Callable[[int], None] | None = None,
        on_node: Callable[[Node, str], None] | None = None,
        dry_run: bool = False,
    ) -> None: ...
    def stop(self) -> None: ...
    def run(self) -> int: ...  # число выполненных действий
```

- `run()`: рекурсивный обход; `on_node(node, path)` перед каждым узлом
  (включая контейнеры и каждую итерацию цикла); `on_step(count)` после
  каждого действия (click/double_click/move/drag/delay/key/scroll).
- `dry_run=True` — проверка плана без реального ожидания пауз; бесконечный
  цикл в этом режиме выполняется один раз (иначе проверка не завершится).
- Остановка: перед узлом и каждой итерацией; `delay` — `stop.wait(seconds)`.
  Прерванный прогон просто возвращает управление (воркер выставит `STOPPED`).
- `FailsafeTriggered` пропускается как есть; ошибки бэкенда оборачиваются
  в `ScenarioRuntimeError` с путём узла и `__cause__`.
- `IfNode` → `ScenarioRuntimeError("Узел 'if' пока не поддерживается — условия
  появятся в следующих версиях")`.

### 4. `core/scenario_runner.py` — сценарий в фоновом потоке

```python
class ScenarioRunner(ThreadedWorker):
    def __init__(
        self,
        backend: InputBackend,
        scenario: Scenario,
        on_step: Callable[[int], None] | None = None,
        on_node: Callable[[Node, str], None] | None = None,
        on_finish: Callable[[StopReason, str], None] | None = None,
    ) -> None: ...
```

- `_run_body(stop)` создаёт `Interpreter` с тем же `stop` и запускает;
  события интерпретатора пробрасываются наружу (в GUI их будет принимать
  адаптер в M4).
- Поведение `start/stop/join/is_running` — как у `Executor`.

### 5. `core/ir/storage.py` — файлы `.acl.json`

```python
SCENARIO_SUFFIX = ".acl.json"


class ScenarioFileError(Exception):
    """Файл сценария не найден/не читается/не записывается."""


def load_scenario(
    path: Path,
) -> Scenario: ...  # OSError → ScenarioFileError; JSON → schema
def save_scenario(
    scenario: Scenario, path: Path
) -> Path: ...  # атомарно, UTF-8, indent=2
def default_scenarios_dir() -> Path: ...  # %APPDATA%\ClicKit\scenarios
```

- Атомарная запись: `path.with_name(path.name + ".tmp")` + `os.replace`
  (как в `SettingsStore`); каталоги создаются.
- Ошибки чтения/записи заворачиваются в `ScenarioFileError` с понятным
  текстом; ошибки содержимого — `ScenarioValidationError`.

### 6. `scripts/run_scenario.py` — консольный запуск

```
python scripts/run_scenario.py resources/examples/click_pause_loop.acl.json
python scripts/run_scenario.py file.acl.json --dry-run
```

- Аргументы: путь к `.acl.json`, `--dry-run` (проверка и подсчёт действий
  без реального ввода), `--no-hotkeys` (для CI/тестов).
- Запуск сразу после старта; `F6` — стоп, `Esc` — выход (как в M1-демо).
- Прогресс: `Действие: N`; по завершении — человекочитаемая причина
  (`Сценарий выполнен` / `Остановлено` / fail-safe / текст ошибки).
- Коды выхода: `0` — успех, `1` — ошибка исполнения/файла, `2` — невалидный сценарий.
- Dry-run прогоняет интерпретатор в режиме `dry_run` (без ввода и пауз,
  бесконечный цикл — один раз) и печатает число действий — автопроверка
  критерия «исполняется из JSON» без мыши.

### 7. `resources/examples/click_pause_loop.acl.json` — пример по критерию

Сценарий: клик → пауза 0.5 с → цикл 10×(движение 0.2 с + клик).
Координаты — безопасные (400,300 → 600,300), не аварийный угол `(0,0)`.
Файл также используется в тестах и dry-run.

### 8. Тесты

- `tests/test_worker.py`: общий воркер — `COMPLETED`/`STOPPED`/`FAILSAFE`/
  `ERROR`, `on_finish` ровно один раз (через подкласс-заглушку).
  Существующие `tests/test_executor.py` остаются без изменений и должны
  быть зелёными (регрессия рефакторинга).
- `tests/test_ir_schema.py`: все узлы — round-trip; дефолты; `id` сохраняется;
  ошибки: нет/неверная версия, пустой `nodes`, неизвестный тип, неверные типы
  полей, диапазоны, кнопка, клавиши, `loop.times`, пустые `children`,
  глубина, лимит узлов, дубли `id`; несколько ошибок с путями; неизвестные
  ключи игнорируются; `if` разбирается структурно.
- `tests/test_ir_interpreter.py`: порядок вызовов; циклы и вложенные циклы;
  бесконечный цикл + стоп; прерывание `delay`; счётчики `on_step`;
  последовательность `on_node` и `id`; fail-safe проходит; ошибка бэкенда
  обёрнута с путём; `if` → понятная ошибка; пустой стоп-флаг до старта.
- `tests/test_scenario_runner.py`: 4 причины завершения; `is_running`;
  `join`; повторный запуск; события доходят.
- `tests/test_ir_storage.py`: save/load round-trip, кириллица в `name`,
  атомарность, создание каталогов, отсутствующий файл, битый JSON,
  не-объект JSON, невалидный сценарий из файла.
- `tests/test_cli_scenario.py`: `parse_args`; dry-run по примеру из
  `resources/examples/` → код 0 и ожидаемое число шагов; невалидный файл → 2;
  отсутствующий → 1 (без запуска слушателя хоткеев).

### 9. Документация

- `PROGRESS.md`: журнал по шагам, «Текущий статус» → M3 завершён,
  следующие шаги → M4; итог по тестам/ruff.
- `AI_CONTEXT.md`: §3.2 — `core/worker.py`, `core/scenario_runner.py`,
  `core/ir/{schema,interpreter,storage}.py`, `scripts/run_scenario.py`,
  `resources/examples/`; §3.3 — ADR №13–17; дата обновления.
- `ROADMAP.md`: статус/детали M3 (рекордер отложен, `if` — резерв).
- `README.md`: статус M3 (сценарии как данные), roadmap ✅, команда
  консольного запуска сценария, пример и ограничение «GUI-редактор — M4».
- `.gitignore`: новых артефактов не ожидается (тестовые сценарии — во
  временных каталогах pytest); проверить, что `.tmp`-файлы сценариев не
  попадают в индекс.

### 10. Коммиты (ветка `feat/m3-ir-scenarios`)

1. `refactor: общий потоковый воркер для Executor`
2. `feat: IR-схема сценария — узлы, валидация, версия`
3. `feat: интерпретатор IR → InputBackend`
4. `feat: потоковый запуск сценария (ScenarioRunner)`
5. `feat: сохранение/загрузка сценариев .acl.json`
6. `feat: консольный запуск сценария и пример`
7. `test: схема, интерпретатор, runner, storage, CLI`
8. `docs: M3 завершён — PROGRESS, ROADMAP, AI_CONTEXT, README`

## Чек-лист приёмки

Автоматически проверено (2026-10-26): `ruff check .` — 0, `ruff format --check .` —
чисто, `pytest` — 117 passed; пример проходит `--dry-run` (22 действия),
CLI-тесты проверяют коды 0/1/2, интерпретатор и runner — на mock-бэкенде.

- [x] Пример `resources/examples/click_pause_loop.acl.json` проходит валидацию
- [x] `--dry-run` печатает число действий (22: 1 клик + 1 пауза + 10×(движение+клик))
- [x] Реальный запуск: сценарий исполняется, `F6` останавливает, `Esc` выходит
- [x] Битый/невалидный файл → понятное сообщение и код 2, без traceback
- [x] Бесконечный цикл останавливается `F6` (в т.ч. внутри `delay`) — покрыто тестами
- [x] `pytest` — зелёные, `ruff check .` / `ruff format --check .` — чисто
- [x] Документация и `.gitignore` обновлены; ветка влита в `master`

## Статус реализации (2026-10-26)

**M3 принят пользователем (2026-10-26), ветка влита в `master` и запушена в `origin`.**

- Реализованы все шаги 1–9; отличия от плана:
  - узлы вынесены в отдельный модуль `core/ir/nodes.py` (`schema.py` только
    разбирает и проверяет JSON) — иначе один файл переваливал за 300 строк;
  - `Interpreter(dry_run=True)` вместо отдельного «принтера плана»: dry-run
    использует тот же обход, что и реальное исполнение (∞-цикл — один раз);
  - CLI запускается сразу (без `F5`), `--start` не понадобился; коды выхода
    0/1/2 покрыты тестами.
- Ручная приёмка: пример отработал 22 действия и завершился со статусом
  «Сценарий выполнен».
- Коммиты (ветка `feat/m3-ir-scenarios`) — 9 шт., по шагам плана.
- Итог: 117 автотестов (было 39), `ruff` чист.

## После M3

- **M4:** Blockly в `resources/blockly/`, транслятор Blockly-JSON → IR,
  подсветка текущего блока через готовый `on_node(node, path)`, `QWebChannel`-мост.
- **M5 / позже:** условия (`if`, `while`) с чтением экрана, `recorder.py`,
  настройки сценариев в `%APPDATA%\ClicKit\scenarios`.
