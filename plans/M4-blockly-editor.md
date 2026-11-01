# M4 — Визуальное программирование: Blockly

> План согласован с пользователем (2026-10-27).
> Критерий готовности (ROADMAP): пользователь собирает сценарий drag-and-drop,
> запускает его и видит пошаговое выполнение; сценарий сохраняется и открывается.
> `ruff check .` — 0 ошибок, `ruff format --check .` — чисто, `pytest` — зелёные.

## Параметры (согласованные)

| Параметр | Значение |
|----------|----------|
| Blockly | **13.4.0**, vendored в `resources/blockly/`, без CDN и без сборки (UMD-скрипты) |
| Состав вендоринга | `blockly_compressed.js`, `blocks_compressed.js`, `msg/ru.js`, `media/*`, `LICENSE` + `VERSION.txt`; воспроизводимый загрузчик `scripts/vendor_blockly.py` |
| Формат сохранения | **гибридный `.acl.json`**: IR — источник исполнения, `editor.workspace` — точное состояние Blockly |
| Тулбар | **внутри веб-страницы** (HTML): запуск, стоп, сохранить, открыть, новый, undo/redo, имя, индикатор «не сохранено» |
| Хоткеи | **контекстные**: F5 запускает активный режим (клики / сценарий), F6 останавливает и клики, и сценарий |
| Язык UI | русский; подписи блоков и категорий — русские |
| Рендерер | `zelos` (вид «как в Scratch»), кастомная тёмная тема под `dark.qss` |
| Взаимное исключение | клики и сценарий не выполняются одновременно; второй запуск отклоняется с подсказкой |
| Вне объёма M4 | `if`/`while`, recorder, пикер координат в поле блока, светлая тема, выбор файла через drag-and-drop |
| Git | ветка `feat/m4-blockly-editor`, коммиты по шагам, затем merge в `master` |

## Архитектурные решения (ADR)

18. **Blockly 13.4.0 — pinned vendor, без CDN.** В репозиторий кладётся только
    рантайм-подмножество (core + стандартные блоки + русские сообщения + media),
    генераторы кода (`javascript_compressed.js` и др.) не нужны: IR собирается
    сериализацией workspace, а не генерацией кода. Обновление версии — только
    через `scripts/vendor_blockly.py`; вендоренные файлы не редактируются.
    Лицензия Blockly — Apache-2.0, `LICENSE` копируется рядом.
    Проверено на текущем окружении: страница грузится с `file://`, `inject`,
    `Blockly.serialization.workspaces.load/save`, `workspace.highlightBlock`,
    `workspace.cleanUp()` и QWebChannel работают.
19. **Гибридный файл сценария.** `.acl.json` остаётся валидным IR-файлом
    (`version`, `name`, `nodes`), но дополнительно может содержать
    `editor: {"kind": "blockly", "workspace": <Blockly-JSON>}`. Схема IR
    игнорирует неизвестные ключи верхнего уровня (ADR №14), поэтому CLI и
    старые файлы M3 работают без изменений. Источник истины для исполнения —
    `nodes`; `editor.workspace` — состояние редактора для точного восстановления
    холста (позиции, отключённые блоки). При открытии состояние сверяется:
    если workspace даёт другой IR, чем `nodes` (файл правили вручную), блоки
    восстанавливаются из IR, а пользователь видит пояснение в статусе.
20. **Валидация — одна, из IR-схемы.** Транслятор Blockly → IR не дублирует
    диапазоны и типы: он собирает IR-словарь с `id` узлов = `id` блоков,
    затем вызывает `scenario_from_mapping`. Ошибки `ScenarioValidationError`
    сопоставляются с блоками по пути (`nodes[2].children[0].x` → узел с `id`),
    и подсвечиваются в редакторе. Структурные ошибки Blockly (неизвестный тип
    блока) дают `BlocklyIssue` сразу с `id` блока.
21. **`sequence` разворачивается, hat-блок не вводится.** IR-узел `sequence`
    семантически равен «выполнить детей подряд», поэтому при обратной
    трансляции он разворачивается в текущий стек (с сохранением `id` детей);
    прямого блока «группа» нет. Блок «когда сценарий запущен» не добавляется:
    IR не событийный, корневой стек выполняется сверху вниз, декоративный
    hat-блок только путал бы. Узел `if` в M4 в палитру не выводится.
22. **QWebChannel — единственный мост; тулбар живёт в HTML.** JS → Python:
    слоты `run/stop/save/open/new_document/ready/log`. Python → JS: сигналы
    `scenario_loaded/node_started/step_done/run_finished/issues_found/
    status_changed/document_saved/running_changed`. Диалоги файлов — в bridge
    (GUI-поток), с инъекцией для тестов. Все файловые операции и запуск
    проверяют ввод; JS-код из workspace не исполняется.
23. **Контекстные хоткеи и защита от двух прогонов.** F5 на вкладке
    «Редактор сценариев» запускает сценарий, на «Простом режиме» — клики;
    F6 останавливает оба вида работы всегда. Запуск кликов при работающем
    сценарии (и наоборот) отклоняется с сообщением. Это исключает два
    потока, одновременно двигающих единственный курсор Windows.

## Блоки (палитра на русском)

| Категория (цвет) | Блок | Поля / входы | IR-узел |
|---|---|---|---|
| Мышь (`#4C97FF`) | `ck_click` — «клик в x: _ y: _ кнопкой _» | `X`, `Y`, `BUTTON` (левой/правой/средней) | `click` |
| Мышь | `ck_double_click` — «двойной клик …» | `X`, `Y`, `BUTTON` | `double_click` |
| Мышь | `ck_move` — «переместить курсор в x: _ y: _ за _ сек» | `X`, `Y`, `DURATION` | `move` |
| Мышь | `ck_drag` — «перетащить в x: _ y: _ за _ сек кнопкой _» | `X`, `Y`, `DURATION`, `BUTTON` | `drag` |
| Мышь | `ck_scroll` — «прокрутить на _» | `AMOUNT` | `scroll` (без точки) |
| Мышь | `ck_scroll_at` — «прокрутить на _ в точке x: _ y: _» | `AMOUNT`, `X`, `Y` | `scroll` (с точкой) |
| Клавиатура (`#9966FF`) | `ck_key` — «нажать клавиши _» | `KEYS` (текст, напр. `ctrl+s`) | `key` |
| Задержки (`#FFAB19`) | `ck_delay` — «пауза _ сек» | `SECONDS` | `delay` |
| Циклы (`#59C059`) | `ck_loop` — «повторить _ раз: _» | `TIMES`, вход `DO` | `loop` (`times` = N) |
| Циклы | `ck_loop_forever` — «повторять бесконечно: _» | вход `DO` | `loop` (`times` = null) |

Правила трансляции:

- `id` IR-узла = `id` блока Blockly (Blockly принимает произвольные строки,
  включая кириллицу и пробелы — проверено); обратная трансляция использует
  `id` узла, а при его отсутствии генерирует `ck-auto-<n>` (уникальный в сценарии).
- Отключённые блоки (`disabledReasons: ["MANUALLY_DISABLED"]` в Blockly 13)
  пропускаются с предупреждением в статусе; точное состояние восстанавливается
  из `editor.workspace`.
- Координаты и счётчики (`x`, `y`, `amount`, `times`) округляются до целого
  (Blockly `field_number` может дать float); `duration`/`seconds` — float.
- Пустой вход `DO` у цикла, пустой холст, неизвестный тип блока, битые поля —
  ошибка с человекочитаемым текстом; блок подсвечивается, запуск/сохранение
  не выполняются.
- Обратная трансляция не задаёт координаты блоков: после загрузки JS вызывает
  `workspace.cleanUp()` (авто-раскладка).
- `sequence` разворачивается (ADR №21); при обратной трансляции `if` невозможен
  (в M3 `if` в IR лишь резерв, в палитре его нет).

## Формат `.acl.json`

```json
{
  "version": 1,
  "name": "Клик → пауза → цикл",
  "nodes": [
    {"type": "click", "id": "blk1", "x": 400, "y": 300},
    {"type": "delay", "id": "blk2", "seconds": 0.5},
    {"type": "loop", "id": "blk3", "times": 3, "children": [
      {"type": "move", "id": "blk4", "x": 600, "y": 300, "duration": 0.2},
      {"type": "click", "id": "blk5", "x": 600, "y": 300}
    ]}
  ],
  "editor": {
    "kind": "blockly",
    "workspace": {"blocks": {"languageVersion": 0, "blocks": ["…"]}}
  }
}
```

- `editor` необязателен: файлы M3 и сценарии, собранные вручную, открываются
  обратной трансляцией IR → блоки.
- `nodes` всегда пересобираются транслятором при сохранении из редактора.

## Модули и интерфейсы

### `bridge/blockly_ir.py` — трансляторы (чистый Python, без Qt)

```python
@dataclass(frozen=True)
class BlocklyIssue:
    block_id: str | None      # None — ошибка не привязана к блоку
    message: str

class BlocklyTranslationError(ValueError):
    issues: tuple[BlocklyIssue, ...]

def workspace_to_scenario(
    workspace: Mapping[str, Any], name: str = ""
) -> Scenario: ...

def scenario_to_workspace(scenario: Scenario) -> dict[str, Any]: ...
```

- `workspace_to_scenario` принимает полный JSON `Blockly.serialization.workspaces.save`
  (`{"blocks": {"languageVersion": …, "blocks": [...]}}`), идёт по цепочкам
  `next` и входу `DO`, собирает IR-словарь и валидирует его через
  `core.ir.schema.scenario_from_mapping`.
- `_node_id_for_path(mapping, path)` — разбор пути IR (`nodes[2].children[0].x`,
  `nodes[1].then`, …) до `id` узла; используется для подсветки.
- `scenario_to_workspace` строит JSON для `Blockly.serialization.workspaces.load`:
  стек корневых блоков, `next`-цепочки, `inputs.DO`, поля блоков; `sequence`
  разворачивается; без координат.

### `bridge/scenario_file.py` — гибридный файл сценария

```python
@dataclass(frozen=True)
class ScenarioDocument:
    scenario: Scenario
    workspace: dict[str, Any] | None

def load_document(path: str | Path) -> ScenarioDocument: ...
def save_document(
    scenario: Scenario,
    path: str | Path,
    workspace: Mapping[str, Any] | None = None,
) -> Path: ...
def resolve_workspace(document: ScenarioDocument) -> tuple[dict[str, Any], bool]:
    """Вернуть (Blockly-JSON, восстановлено_из_IR)."""
```

- `load_document`: читает JSON, проверяет IR через `scenario_from_mapping`;
  `editor.workspace` берёт только если это объект, иначе игнорирует (лог).
  Ошибки IO/JSON — `ScenarioFileError`, содержимое — `ScenarioValidationError`.
- `save_document`: атомарная запись (общий helper из `core/ir/storage.py`),
  добавляет `editor` только при наличии workspace.
- `resolve_workspace`: если workspace есть — транслирует его и сравнивает
  `to_mapping()` с IR файла; при совпадении отдаёт workspace, иначе (или при
  ошибке трансляции) — `scenario_to_workspace(scenario)` и флаг `True`.

### `core/ir/storage.py` — небольшой рефакторинг

Вынести атомарную запись в `write_json(path, payload) -> Path`
(UTF-8, `indent=2`, временный файл + `os.replace`, ошибки → `ScenarioFileError`);
`save_scenario` использует его. Публичный API M3 не меняется.

### `gui/editor/scenario_adapter.py` — Qt-адаптер сценария

```python
class ScenarioAdapter(QObject):
    started = Signal()
    step = Signal(int)            # выполнено действий
    node_started = Signal(str)    # id блока ("" если id нет)
    finished = Signal(str, str)   # StopReason.value, detail

    def __init__(self, backend: InputBackend, parent: QObject | None = None) -> None: ...
    @property
    def is_running(self) -> bool: ...
    def start(self, scenario: Scenario) -> bool: ...
    def stop(self, wait: bool = False) -> None: ...
```

- Устройство как у `ExecutorAdapter` (ADR №11): номер прогона, отбрасывание
  событий устаревшего прогона, `ScenarioRunner` в фоне, сигналы в GUI-поток.
- `node_started` эмитит `node.id or ""`; последний подсвеченный блок остаётся
  подсвеченным при ошибке (в статусе — путь узла из `detail`).

### `bridge/web_channel.py` — QWebChannel-мост

```python
class ScenarioBridge(QObject):
    # Python → JS
    scenario_loaded = Signal(str, str)   # name, workspace JSON
    node_started = Signal(str)
    step_done = Signal(int)
    run_finished = Signal(str, str)      # reason, понятное сообщение
    issues_found = Signal(str)           # JSON: [{"block_id": str|None, "message": str}]
    status_changed = Signal(str, bool)   # текст, ошибка?
    document_saved = Signal(str, str)    # path, name
    running_changed = Signal(bool)

    def __init__(
        self,
        adapter: ScenarioAdapter,
        open_dialog: Callable[[], str | None] | None = None,
        save_dialog: Callable[[str], str | None] | None = None,
        dialog_parent: QWidget | None = None,
        parent: QObject | None = None,
    ) -> None: ...

    # JS → Python (слоты)
    @Slot(str, str)
    def run(self, name: str, workspace_json: str) -> None: ...
    @Slot()
    def stop(self) -> None: ...
    @Slot(str, str)
    def save(self, name: str, workspace_json: str) -> None: ...
    @Slot()
    def open(self) -> None: ...
    @Slot()
    def new_document(self) -> None: ...
    @Slot()
    def ready(self) -> None: ...
    @Slot(str)
    def log(self, message: str) -> None: ...
```

- `run`: разбор JSON → трансляция → при ошибках `issues_found` + `status_changed`
  (без запуска); при успехе — `adapter.start` (отказ, если сценарий уже идёт).
- `save`: при отсутствии текущего пути — диалог сохранения (имя из поля,
  каталог `default_scenarios_dir()`); после успеха `document_saved`.
- `open`: диалог → `load_document` → `resolve_workspace` → `scenario_loaded`;
  при восстановлении из IR — поясняющий статус. `new_document` сбрасывает
  текущий путь, чтобы «Сохранить» спросил новый файл.
- Диалоги по умолчанию — `QFileDialog` с фильтром `Сценарии ClicKit (*.acl.json)`;
  инъекция позволяет тестировать слоты без модальных окон.
- Соединения `adapter.*` → сигналы моста создаются в конструкторе; сообщения
  о завершении строятся по `StopReason` (как в `MainWindow`).

### `gui/editor/editor_view.py` — вкладка редактора

```python
class EditorView(QWidget):
    status_message = Signal(str, bool)
    running_changed = Signal(bool)

    def __init__(self, backend: InputBackend, parent: QWidget | None = None) -> None: ...
    def request_run(self) -> None: ...
    def request_stop(self) -> None: ...
    @property
    def is_running(self) -> bool: ...
    def shutdown(self) -> None: ...
```

- `QWebEngineView` + `QWebEnginePage` (логи JS-консоли → `logging`),
  `QWebChannel` с `ScenarioBridge`, загрузка `resources/blockly/index.html`.
- `request_run` для F5: `runJavaScript("editorApi.exportForRun()", callback)` →
  `bridge.run(name, workspace_json)` (JS-сторона для кнопки тулбара делает это
  напрямую).
- `request_stop` → `bridge.stop()`; `shutdown` — `adapter.stop(wait=True)`.
- Заменить заглушку `gui/editor/editor_view.py` (сохранив имя класса).

### `gui/main_window.py` — интеграция

- Вкладка редактора = `EditorView(self._adapter.backend)`; вкладки и подписи
  не меняются.
- `editor.status_message` → статус-бар; `editor.running_changed` → трей
  (`set_running(clicks or scenario)`) и защита от двойного запуска.
- Хоткеи: `F5` → `_start_active_mode()` (редактор → сценарий, иначе клики);
  `F6` → `_stop_all()` (оба). Трей «Старт (F5)» → `_start_active_mode()`,
  «Стоп» → `_stop_all()`.
- `_start_clicks` отклоняется при работающем сценарии; `_start_scenario` —
  при работающих кликах; сообщение «Сначала остановите … (F6)».
- `_shutdown`: `editor.shutdown()` до сохранения настроек.
- Обновить `HOTKEY_HINT` (F5 — старт активного режима).

### `resources/blockly/` — страница редактора

| Файл | Назначение |
|---|---|
| `index.html` | каркас страницы: тулбар, `blocklyDiv`, статус, подключение скриптов (Blockly, `msg/ru.js`, наши файлы) |
| `blocks.js` | 10 определений блоков + подсказки (tooltips) на русском |
| `theme.js` | тёмная тема `clickitDark` (фон `#1e1f22`, панели `#232428`/`#2b2d31`, акцент `#5865f2`, границы `#3a3d43`) |
| `editor.js` | inject workspace (zelos, grid, zoom, trashcan, звуки выкл.), стартовый пример, тулбар, dirty-флаг, undo/redo, QWebChannel, подсветка, ошибки, `editorApi.exportForRun()` |
| `editor.css` | стили тулбара/статуса под `dark.qss`, подсветка выполняемого блока |
| `VERSION.txt` | версия и источник вендоринга |
| `blockly_compressed.js`, `blocks_compressed.js`, `ru.js`, `media/*`, `LICENSE` | вендоренный Blockly 13.4.0 |

- Стартовый пример (при открытии вкладки): «клик (400,300) → пауза 0.5 →
  повторить 3×(переместить (600,300) 0.2 → клик (600,300))» — совпадает с
  `resources/examples/click_pause_loop.acl.json` и служит демо.
- `document.title`/тулбар показывают имя и точку «не сохранено»; Ctrl+S —
  сохранить, Ctrl+O — открыть; Ctrl+Z/Ctrl+Y обрабатывает сам Blockly.
- Подсветка: `workspace.highlightBlock(id)` + CSS-класс `ck-running`
  (яркая обводка) на время выполнения; предыдущая подсветка снимается.
- Ошибки: `block.setWarningText(message)` + центрирование на первом блоке;
  предупреждения снимаются перед каждым запуском/сохранением.

### `scripts/vendor_blockly.py` — воспроизводимый вендоринг

```
python scripts/vendor_blockly.py            # скачать и обновить resources/blockly
python scripts/vendor_blockly.py --check    # только проверить наличие файлов
```

- Пин `BLOCKLY_VERSION = "13.4.0"`, tarball с `registry.npmjs.org`, распаковка
  во временный каталог, копирование только нужных файлов, запись `VERSION.txt`.
- Сеть нужна только разработчику; рантайм и тесты работают офлайн.
- Наши файлы (`index.html`, `blocks.js`, `theme.js`, `editor.js`, `editor.css`)
  скрипт не трогает.

## Шаги

1. **Вендоринг Blockly.** `scripts/vendor_blockly.py`, `resources/blockly/*`
   (только вендоренные файлы + `VERSION.txt`), проверка загрузки страницы.
2. **Трансляторы.** `bridge/blockly_ir.py`: forward/backward, `BlocklyIssue`,
   маппинг путей IR → `id` блока, разворачивание `sequence`, пропуск
   отключённых блоков, округление чисел, защита глубины.
3. **Гибридный файл.** `core/ir/storage.py::write_json`,
   `bridge/scenario_file.py` (`ScenarioDocument`, `load_document`,
   `save_document`, `resolve_workspace`).
4. **Адаптер и мост.** `gui/editor/scenario_adapter.py`,
   `bridge/web_channel.py` (слоты, сигналы, диалоги с инъекцией).
5. **Страница редактора.** `resources/blockly/{index.html,blocks.js,theme.js,
   editor.js,editor.css}`: палитра, тема, стартовый пример, тулбар, подсветка,
   ошибки, QWebChannel, `editorApi`.
6. **Интеграция в окно.** `gui/editor/editor_view.py` (webview + канал),
   `gui/main_window.py` (контекстные хоткеи, взаимное исключение, трей,
   завершение), `tests/conftest.py` (флаги WebEngine для offscreen).
7. **Тесты.** Трансляторы, файл, адаптер, мост, web-смоук, обновление
   GUI-смоука (см. ниже).
8. **Документация.** `PROGRESS.md`, `AI_CONTEXT.md` (§3.1–§3.3, §4),
   `ROADMAP.md`, `README.md`; проверка `.gitignore`.

## Тесты

- `tests/test_blockly_ir.py`
  - forward: каждый тип блока → нужный узел; дефолты и округление; конечный и
    бесконечный цикл; `scroll` с точкой и без; порядок цепочек и вложенность;
    `id` = `id` блока; отключённый блок пропускается; неизвестный тип → ошибка
    с `id`; пустой холст → ошибка без `id`; пустое тело цикла → ошибка с `id`
    цикла; глубина > `MAX_DEPTH`; неверный `x`/`keys` → ошибка привязана к блоку.
  - backward: все узлы IR → workspace JSON → forward → `to_mapping()` совпадает;
    `sequence` разворачивается; `id` сохраняются; без `id` генерируются
    уникальные; бесконечный цикл; варианты `scroll`.
- `tests/test_scenario_file.py`
  - save/load с workspace и без; `editor` не ломает IR; битый `editor`
    игнорируется; атомарность (нет `.tmp`); кириллица в имени; отсутствующий
    файл/битый JSON; `resolve_workspace`: совпадение, расхождение с `nodes`,
    невалидный workspace → флаг «восстановлено из IR».
- `tests/test_scenario_adapter.py`
  - `COMPLETED`/`STOPPED`/`FAILSAFE`/`ERROR`; `node_started` с `id` в порядке
    выполнения; `step`; `is_running`; повторный запуск; `join`.
- `tests/test_web_channel.py`
  - `run` с валидным workspace → `running_changed(True)` → `run_finished`;
  `run` с пустым/битым → `issues_found`, запуска нет; `save` с инъекцией
  диалога → файл создан, `document_saved`, повторное сохранение без диалога;
  `open` с инъекцией → `scenario_loaded`, `new_document` сбрасывает путь;
  битый JSON → понятный статус.
- `tests/test_editor_web.py` (offscreen, помечен как «медленный», пропускается
  при `CLICKIT_SKIP_WEB=1`)
  - страница загружается, `window.__ckReady === true`; стартовый workspace
    содержит блоки; `editorApi.exportForRun()` возвращает валидный JSON;
    `editorApi.highlightBlock(id)` находит блок.
- `tests/test_gui_smoke.py`
  - существующие тесты остаются зелёными; вкладка редактора — `EditorView`;
    взаимное исключение кликов и сценария; F5-роутинг по активной вкладке.
- `tests/conftest.py`: до импорта Qt — `QTWEBENGINE_DISABLE_SANDBOX=1`,
  `QTWEBENGINE_CHROMIUM_FLAGS=--disable-gpu` (только для тестов).

## Документация

- `PROGRESS.md`: записи по шагам, «Текущий статус» → M4 завершён, следующие
  шаги → M5 (полировка, упаковка), итог по тестам/ruff.
- `AI_CONTEXT.md`:
  - §3.1 — Blockly в `QWebEngineView`, JS↔Python только через QWebChannel,
    вендоренный Blockly без сети;
  - §3.2 — `bridge/{blockly_ir,scenario_file,web_channel}.py`,
    `gui/editor/{editor_view,scenario_adapter}.py`, заполненный
    `resources/blockly/`, `scripts/vendor_blockly.py`;
  - §3.3 — ADR №18–23; §4 — правило «вендоренные файлы Blockly не редактируем,
    обновляем скриптом»;
  - дата последнего обновления.
- `ROADMAP.md`: статус M4, уточнения (hat-блок не вводится, `if` — после M4).
- `README.md`: статус M4, возможности редактора, как собрать/запустить
  сценарий, ограничения (Blockly локально, интернет не нужен).
- `.gitignore`: вендоренные файлы коммитятся; проверить, что временные
  артефакты загрузчика/тестов не попадают в индекс (при необходимости
  добавить `resources/blockly/*.tgz`).

## Коммиты (ветка `feat/m4-blockly-editor`)

1. `chore: вендоринг Blockly 13.4.0 и скрипт обновления`
2. `feat: транслятор Blockly-JSON ↔ IR`
3. `feat: гибридный файл сценария (IR + editor.workspace)`
4. `feat: адаптер сценария и QWebChannel-мост`
5. `feat: страница редактора Blockly (блоки, тема, тулбар)`
6. `feat: вкладка редактора и контекстные хоткеи`
7. `test: трансляторы, файл, адаптер, мост, web-смоук`
8. `docs: M4 завершён — PROGRESS, ROADMAP, AI_CONTEXT, README`

## Чек-лист приёмки

Автоматически:

- [x] `ruff check .` — 0 ошибок, `ruff format --check .` — чисто
- [x] `pytest` — зелёные (включая web-смоук; при необходимости
      `CLICKIT_SKIP_WEB=1` для сред без WebEngine)
- [x] forward/backward round-trip всех типов узлов, ошибки с `id` блоков
- [x] гибридный файл: `nodes` валиден для CLI M3, `editor.workspace`
      восстанавливается; ручная правка `nodes` → fallback из IR
- [x] сценарий запускается с mock-бэкендом, события `node_started` доходят

Вручную (пользователь) — пройдено 2026-10-27:

- [x] Вкладка «Редактор сценариев»: палитра на русском, тёмная тема, стартовый
      пример из блоков
- [x] Сборка сценария drag-and-drop, запуск кнопкой и `F5`, подсветка текущего
      блока, мгновенный стоп `F6` (в т.ч. внутри паузы и бесконечного цикла)
- [x] Сохранение в `.acl.json`, повторное открытие — холст восстанавливается;
      открытие `resources/examples/click_pause_loop.acl.json` — блоки из IR
- [x] Ошибка «пустое тело цикла» подсвечивает блок и не запускает/не сохраняет
      сценарий
- [x] Undo/redo, имя сценария, индикатор «не сохранено», Ctrl+S/Ctrl+O
- [x] Клики и сценарий не запускаются одновременно; подсказка предлагает F6
- [x] Закрытие приложения во время выполнения сценария останавливает его

## Риски и смягчение

| Риск | Смягчение |
|---|---|
| QtWebEngine/PyInstaller (M5) — вендоренные файлы нужно включить в `datas` | Зафиксировать в плане M5; сейчас проверить запуск из исходников и offscreen-тесты |
| Blockly 13 меняет API сериализации/темы | Версия pinned; `scripts/vendor_blockly.py`; тесты трансляторов не зависят от JS |
| WebEngine-тесты нестабильны в CI | Один смоук-тест с таймаутом, пропуск через `CLICKIT_SKIP_WEB=1`; основная логика — чистый Python |
| Трансляция 10 000 узлов в GUI-потоке | Лимит IR уже 10 000; замер на тестах, при необходимости — вынести в поток позже |
| Модальные диалоги из QWebChannel-слота | Слоты живут в GUI-потоке; диалоги инъектируются в тестах |
| Несовпадение `editor.workspace` и `nodes` после ручной правки | `resolve_workspace` сверяет и восстанавливает из IR с пояснением |

## После M4

- **M5:** полировка, светлая тема, настройки хоткеев/языка, логи, PyInstaller
  (включая `resources/blockly/` в `datas`), NOTICE о LGPL/Apache-2.0.
- **Позже:** условия `if`/`while` с чтением экрана (пиксель/картинка),
  `recorder.py`, пикер координат прямо в поле блока, библиотека шаблонов.

## Статус реализации (2026-10-27)

**M4 принят пользователем 2026-10-27 и влит в `master`** (ветка
`feat/m4-blockly-editor`, 10 коммитов). `ruff check .` — 0,
`ruff format --check .` — чисто, `pytest` — 180 passed.

- Реализованы шаги 1–8. Отличия и уточнения:
  - тесты писались вместе с фичами (трансляторы, файл, адаптер, мост), отдельным
    коммитом — web-смоук и смоук интеграции окна (в плане был один общий test-шаг);
  - добавлен **ADR №24**: ленивая загрузка `QWebEngineView` при первом показе
    вкладки и принудительное уничтожение webview в `EditorView.shutdown()` /
    `application.run()` — иначе QtWebEngine на Windows падает на выходе;
  - тулбар адаптивный (перенос кнопок на узких окнах);
  - в `resources/blockly/` добавлен `VERSION.txt`; путь к media задаётся
    опцией `media: 'media/'` при `Blockly.inject` (в Blockly 13 значение
    по умолчанию — CDN, поэтому без этого редактор тянул бы ресурсы из сети);
  - стартовый сценарий загружается с отключёнными событиями Blockly, чтобы
    асинхронные `create`/`finished_loading` не поднимали dirty-флаг;
  - offscreen-тесты WebEngine требуют `QTWEBENGINE_DISABLE_SANDBOX=1`,
    `QTWEBENGINE_CHROMIUM_FLAGS=--disable-gpu` (в `tests/conftest.py`);
    смоук можно отключить `CLICKIT_SKIP_WEB=1`.
- Коммиты ветки: 10 (8 кода/тестов + документация + фиксы по приёмке).
- Ручная приёмка по чек-листу выше пройдена 2026-10-27; ветка влита в `master`.
