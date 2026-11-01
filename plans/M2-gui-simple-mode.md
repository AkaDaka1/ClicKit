# M2 — Главное окно + «Простой режим» (MVP-автокликер)

> План согласован с пользователем (2026-10-25).
> Критерий готовности (ROADMAP): пользователь без консоли настраивает и
> запускает автоклик по точке, аварийный стоп работает;
> `ruff check .` — 0 ошибок, `ruff format --check .` — чисто, `pytest` — зелёные.

## Параметры (согласованные)

| Параметр | Значение |
|----------|----------|
| Интервал | поле «Интервал, мс», целое, 1..3 600 000; в executor передаётся в секундах |
| Повторы | число + галочка «Бесконечно»; по умолчанию 100 повторов |
| Кнопка мыши | Левая / Правая / Средняя |
| Хоткеи | **фиксированные**: `F5` — старт, `F6` — аварийный стоп, `F8` — захват точки; редактирование — M5 |
| Оформление | **тёмная тема** (`resources/styles/dark.qss`), светлая/переключатель — M5 |
| Закрытие окна | диалог с галочкой «Запомнить выбор», два независимых поведения (см. §6) |
| Трей | всегда активен: Показать/Скрыть, Старт, Стоп, Выход |
| Настройки | `%APPDATA%\ClicKit\settings.json` (персист формы, хоткеев, выбора при закрытии) |
| Фоновые клики (без захвата курсора) | **вне M2**: спайк `PostMessage`-бэкенда после вехи (backlog) |
| Git | ветка `feat/m2-gui-simple-mode`, коммиты по шагам, затем merge в `master` |

## Архитектурные решения (ADR)

8. **Настройки — JSON в `%APPDATA%\ClicKit`** (атомарная запись через временный
   файл + `os.replace`), реализация в `core/settings.py` без PySide6. Кривой/
   отсутствующий файл не роняет приложение: дефолты + запись в лог.
9. **Причины завершения исполнения** — `StopReason` (`completed` / `stopped` /
   `failsafe` / `error`) и `on_finish(reason, detail)` в `Executor`. Fail-safe
   pyautogui больше не «traceback», а понятный статус в GUI.
10. **Один `HotkeyManager` на приложение + Qt-мост** (`gui/hotkey_bridge.py`):
    callback'и pynput живут в потоке слушателя и только эмитят Qt-сигналы;
    чтение виджетов/старт — всегда в GUI-потоке.
11. **Executor ↔ GUI — только через адаптер** `gui/executor_adapter.py`
    (`QObject` + сигналы), `core/` остаётся без PySide6.
12. **Ограничение платформы (зафиксировано):** второй независимый курсор мыши
    в Windows невозможен (все устройства сводятся к одному указателю).
    «Клики без захвата курсора» возможны только как `PostMessage` в целевое окно
    (не для всех приложений) — отдельный спайк, а не часть MVP.

## Шаги

### 1. `core/settings.py` — модель и хранилище настроек

```python
"""Настройки приложения: модель, значения по умолчанию, JSON в %APPDATA%."""

SETTINGS_VERSION = 1


@dataclass
class Settings:
    """Пользовательские настройки (простого режима и поведения окна)."""

    x: int = 0
    y: int = 0
    button: str = "left"                 # left|right|middle
    interval_ms: int = 100               # 1..3_600_000
    repeats: int = 100                   # 1..1_000_000_000
    infinite: bool = False
    hotkey_start: str = "<f5>"
    hotkey_stop: str = "<f6>"
    hotkey_pick: str = "<f8>"
    close_action_running: str = "ask"    # ask|tray|quit
    close_action_idle: str = "ask"       # ask|tray|quit

    def normalized(self) -> "Settings": ...   # clamp + откат невалидных значений


class SettingsStore:
    """Загрузка/сохранение настроек в JSON (атомарно, устойчиво к битому файлу)."""

    def __init__(self, path: Path | None = None) -> None: ...
    @staticmethod
    def default_path() -> Path: ...      # %APPDATA%\ClicKit\settings.json
    def load(self) -> Settings: ...      # ошибки → дефолты + logger.warning
    def save(self, settings: Settings) -> None: ...  # mkdir + tmp + replace
```

- `load()` читает `{"version": 1, ...}`; неизвестные ключи игнорируются,
  отсутствующие берут значение по умолчанию; неверные типы → дефолт по полю.
- `save()` создаёт каталог, пишет `settings.json.tmp` и подменяет файл.

### 2. `core/input/backend.py` — `position()` и `FailsafeTriggered`

- Новый метод ABC: `position() -> tuple[int, int]` (позиция курсора; нужен пикеру).
- Новое исключение `FailsafeTriggered(Exception)` — «сработала защита
  pyautogui (курсор в углу экрана)». `core/` не импортирует pyautogui.
- `PyAutoguiBackend`: `position()` → `pyautogui.position()`; декоратор
  `_translate_failsafe` на всех отправляющих методах превращает
  `pyautogui.FailSafeException` в `FailsafeTriggered`.

### 3. `core/executor.py` — причины завершения

```python
class StopReason(Enum):
    COMPLETED = "completed"   # пройдены все повторы
    STOPPED = "stopped"       # вызван stop() / F6
    FAILSAFE = "failsafe"     # FailsafeTriggered от бэкенда
    ERROR = "error"           # любое другое исключение

Executor(..., on_step=None, on_finish: Callable[[StopReason, str], None] | None = None)
```

- `_run()` определяет причину в `finally` и вызывает `on_finish` **один раз**
  в потоке исполнителя; `detail` — текст ошибки/комментарий (или `""`).
- Поведение M1 (команды, интервал, прерываемый сон) не меняется — тесты M1
  остаются зелёными.

### 4. `gui/executor_adapter.py` — Qt-адаптер исполнителя

```python
class ExecutorAdapter(QObject):
    started = Signal()
    stopped = Signal()
    step = Signal(int)                 # выполнено кликов
    finished = Signal(str, str)        # reason.value, detail
    error = Signal(str)
    def start(self, config: SimpleRunConfig) -> None: ...
    def stop(self) -> None: ...
    @property
    def is_running(self) -> bool: ...
```

- Создаёт `Executor` с `create_backend()`, `commands=[Command(CLICK, x, y, button)]`,
  `interval=interval_ms / 1000`, `repeats=None` при «Бесконечно».
- `on_step`/`on_finish` из потока воркера → Qt-сигналы (auto/queued connection).
- Повторный `start()` во время работы игнорируется; события устаревшего прогона
  отбрасываются по номеру прогона (`run_id`), поэтому быстрый «стоп → старт»
  не сбивает состояние формы.

### 5. `gui/hotkey_bridge.py` — глобальные хоткеи → Qt-сигналы

```python
class HotkeyBridge(QObject):
    start_requested = Signal()
    stop_requested = Signal()
    pick_requested = Signal()
    def start(self) -> None: ...
    def stop(self) -> None: ...
```

- Внутри один `HotkeyManager`, регистрация `settings.hotkey_start/stop/pick`.
- Callback'и только эмитят сигналы (никакой работы в потоке слушателя).

### 6. `gui/picker.py` — пикер координат

```python
class CoordinatePicker(QObject):
    captured = Signal(int, int)        # x, y в GUI-потоке
    failed = Signal(str)               # сбой чтения позиции
    def capture(self) -> bool: ...     # снять позицию курсора
```

- Реализовано проще, чем планировалось: `F8` сразу снимает позицию курсора
  (без состояния «взведения» — так меньше кликов у пользователя).
  Кнопка «Захватить точку (F8)» и пункт меню/хоткей делают одно и то же,
  «Текущая позиция» — то же самое, но явно.
- Пока идут клики, захват игнорируется с подсказкой в статус-баре.
- Захват не блокирует окно: пользователь уводит курсор в нужную точку и жмёт F8.

### 7. `gui/simple_mode/config.py` — чистая логика формы

```python
@dataclass(frozen=True)
class SimpleRunConfig:
    """Параметры запуска простого режима (не зависит от Qt)."""

    x: int
    y: int
    button: Button
    interval_ms: int
    repeats: int | None        # None — бесконечно

    def commands(self) -> list[Command]: ...
    def interval_seconds(self) -> float: ...
```

- Валидация в одном месте; тестируется без GUI.

### 8. `gui/simple_mode/view.py` — форма простого режима

- Группа «Точка»: X/Y спинбоксы (диапазон -32 768..32 767 — мультимонитор),
  кнопка «Захватить точку (F8)», кнопка «Текущая позиция».
- Группа «Клики»: кнопка мыши (combo), «Интервал, мс», «Повторов» + «Бесконечно».
- Кнопка-акцент «Старт» / «Стоп» (переключается), счётчик выполненного.
- Сигналы: `start_requested`, `stop_requested`, `pick_requested`.
- Методы: `run_config()`, `apply_settings(settings)`, `set_running(bool)`,
  `set_counter(int)`, `set_message(str)`.
- Невалидные значения (пустой/0 интервал, 0 повторов) → подсветка + сообщение,
  старт не выполняется.

### 9. `gui/editor/editor_view.py` — заглушка редактора

- `EditorView(QWidget)`: заголовок «Визуальный редактор», текст-заглушка
  «Появится в вехе M4 — сценарии из блоков», короткий список будущих
  возможностей. Никакой логики.

### 10. `gui/main_window.py` — главное окно

- Шапка: название/версия + индикатор состояния (точка «Готов» / «Работает»).
- `QTabWidget`: «Простой режим» | «Редактор сценариев» (заглушка).
- Статус-бар: сообщение + постоянная подсказка «F5 — старт · F6 — стоп · F8 — точка».
- Связки: `SimpleModeView` ↔ `ExecutorAdapter` ↔ `HotkeyBridge` ↔ `CoordinatePicker`.
- Сохранение формы в настройки при старте и при выходе; применение при запуске.
- Тема: `app.application` применяет `resources/styles/dark.qss`.

### 11. Закрытие окна и трей (`gui/main_window.py`, `gui/tray.py`)

```python
close_action_running / close_action_idle: "ask" | "tray" | "quit"
```

- Закрытие при **идущих кликах**: вопрос «Клики выполняются. Свернуть ClicKit
  в трей, чтобы их не прерывать?» → [Свернуть в трей] [Остановить и выйти] [Отмена]
  + чекбокс «Запомнить мой выбор».
- Закрытие **без активных кликов**: вопрос «Клики не выполняются. Свернуть
  ClicKit в трей?» → [Свернуть в трей] [Выйти] [Отмена] + чекбокс «Запомнить».
- «Запомнить» сохраняется в настройки (по каждому сценарию отдельно); снимается
  галочка — выбор не запоминается. «Отмена» ничего не запоминает и не закрывает.
- Трей: иконка + меню (Показать/Скрыть, Старт, Стоп, Выход) + подсказка при
  первом сворачивании. Выход из трея — без диалога, с остановкой кликов.
- `QApplication.setQuitOnLastWindowClosed(False)`; окно не «теряется»:
  повторный запуск из меню трея возвращает его.

### 12. `gui/icons.py` + `resources/icons/clicKit.svg` + `resources/styles/dark.qss`

- Иконка приложения — SVG (курсор + шестерёнка «kit»), грузится в `QIcon`,
  используется окном и треем; если файл не читается — простая запасная иконка,
  нарисованная `QPixmap` (без падения приложения).
- Тёмная тема: фон `#1e1f22`, карточки `#2b2d31`, акцент `#5865f2`, текст
  `#e6e6e6`, рамки `#3a3d43`, радиусы 8 px; стилизованы `QTabWidget`,
  `QGroupBox`, `QSpinBox`, `QComboBox`, `QCheckBox`, `QPushButton` (+ `#primary`),
  `QStatusBar`, `QToolTip`, `QMessageBox`.

### 13. `app/application.py` + `app/paths.py`

- `app/paths.py`: `project_root()`, `resource_path(*parts)` — пути к ресурсам
  от корня проекта (устойчиво к запуску из любого каталога); при упаковке
  PyInstaller путь будет браться из `sys._MEIPASS` (M5).
- `application.py`: `SettingsStore` → `Settings` → `MainWindow(settings, store)`;
  `app.setStyleSheet` из файла; иконка приложения; `quitOnLastWindowClosed(False)`.

### 14. Тесты

- `tests/test_settings.py`: дефолты при отсутствии файла; round-trip save/load;
  битый JSON → дефолты; клампинг значений; независимость `close_action_*`;
  атомарность записи; путь `%APPDATA%`.
- `tests/test_executor.py` (+6): `completed`, `stopped`, `failsafe`
  (`MockBackend`, бросающий `FailsafeTriggered`), `error` → `on_finish`
  с правильной причиной; `on_finish` вызывается ровно один раз.
- `tests/test_pyautogui_backend.py`: `FailSafeException` → `FailsafeTriggered`
  (функции pyautogui подменяются, реального ввода нет), `position()`.
- `tests/test_simple_config.py`: `interval_seconds`, `commands()`,
  бесконечные повторы (`repeats is None`), невалидные значения.
- `tests/conftest.py`: `QT_QPA_PLATFORM=offscreen` + общий `QApplication`.
- `tests/test_gui_smoke.py`: окно создаётся, вкладок две; старт кнопкой даёт
  ровно один клик (mock-бэкенд) и возвращает форму в «готов»; захват точки
  заполняет координаты.
- `tests/test_close_dialog.py`: оба диалога закрытия (кнопку нажимает таймер),
  «Запомнить выбор» сохраняется раздельно для двух сценариев, запомненное
  действие применяется без вопроса.
- `tests/test_application.py`: стартовые настройки (первый запуск — центр экрана).
- `tests/test_gui_smoke.py` (+1): точка `(0, 0)` не запускает клики и показывает
  подсказку про аварийный угол pyautogui. Всего 39 тестов.

### 15. Документация и `.gitignore`

- `PROGRESS.md`: журнал по шагам + «Текущий статус» → M2 завершён, следующий M3;
  закрыть пункт про fail-safe («заменён на понятное сообщение») и добавить
  заметку об ограничении платформы (один курсор).
- `ROADMAP.md`: в backlog — «фоновые клики `PostMessage` (спайк после M2)»;
  критерий M2 не меняется.
- `AI_CONTEXT.md`: §3.2 (новые модули), §3.3 ADR №8–12, дата обновления.
- `README.md`: статус M2, функции простого режима (F5/F6/F8, трей, тёмная тема),
  скриншот — если получится снять (иначе в M5).
- `.gitignore`: новых артефактов нет (настройки лежат вне репозитория);
  проверить, что `settings.json` не попадёт в индекс.

### 16. Коммиты (ветка `feat/m2-gui-simple-mode`)

1. `feat: настройки приложения — модель и JSON в %APPDATA%`
2. `feat: position() и FailsafeTriggered в InputBackend`
3. `feat: причины завершения и on_finish в Executor`
4. `feat: Qt-адаптер исполнителя и мост глобальных хоткеев`
5. `feat: пикер координат (F8)`
6. `feat: простой режим — форма, валидация, запуск`
7. `feat: главное окно, вкладки, трей, закрытие с запоминанием`
8. `feat: тёмная тема и иконка приложения`
9. `test: настройки, причины остановки, смоук GUI`
10. `docs: M2 завершён — PROGRESS, ROADMAP, AI_CONTEXT, README`

## Чек-лист приёмки

Автоматически проверено (2026-10-25): `ruff check .` — 0, `ruff format --check .` — чисто,
`pytest` — 39 passed; главное окно собирается, тема применяется (пиксельная проверка
превью), старт/стоп/счётчик работают на mock-бэкенде, диалоги закрытия и «Запомнить
выбор» проверены тестами.

- [x] `python -m app` запускается, процесс живёт, окно в тёмной теме, две вкладки
- [x] Координаты задаются вручную и пикером по F8 (статус-бар подсказывает)
- [x] Старт кнопкой и F5, стоп кнопкой и F6 из любого приложения
- [x] Повторы: N кликов ровно N; «Бесконечно» работает до стопа
- [x] Fail-safe (курсор в углу) → понятное сообщение в статус-баре, без traceback
- [x] Трей: старт/стоп/показать/выход; сворачивание по диалогу
- [x] Диалоги закрытия: два сценария, галочка «Запомнить» работает и сохраняется
- [x] Настройки восстанавливаются после перезапуска (`%APPDATA%\ClicKit\settings.json`)
- [x] `ruff check .` / `ruff format --check .` — чисто; `pytest` — зелёные
- [x] Документация обновлена; ветка влита в `master`

## Статус реализации (2026-10-25)

**M2 принят пользователем (2026-10-25), ветка влита в `master` и запушена в `origin`.**

- Реализованы все шаги 1–15; отличия от плана:
  - пикер: `F8` сразу снимает позицию (без «взведения»), сигналы `captured`/`failed`;
  - `MainWindow(..., backend=..., enable_hotkeys=False)` — параметры для тестов;
  - `Executor.join(timeout)` для корректного завершения при выходе;
  - добавлен `run_id` в `ExecutorAdapter` против гонки «стоп → старт»;
  - первый запуск ставит точку в центр экрана, старт с `(0, 0)` блокируется
    (аварийный угол pyautogui останавливал бы клики со второго раза).
- Коммиты (ветка `feat/m2-gui-simple-mode`) — 12 шт., по шагам плана.
- Итог: 39 автотестов, `ruff` чист, все пункты чек-листа закрыты.

## После M2

- **Спайк:** фоновые клики `PostMessage` в выбранное окно (курсор свободен) —
  прототип + матрица совместимости приложений; решение о включении в продукт.
- **M3:** IR-сценарии (схема, валидация, интерпретатор, сохранение в `.acl.json`).
