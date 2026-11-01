# M5 — Полировка и упаковка

Статус: согласован 2026-10-28, в работе.
Предыдущая веха: M4 (Blockly-редактор) — принят и влит в `master`.

## 1. Цель и критерий готовности

**Цель:** продукт, который не стыдно раздать: аккуратный внешний вид в двух
темах, настраиваемые хоткеи, понятные ошибки и логи, готовый `.exe` без Python.

**Критерий готовности M5 (приёмка):**
1. `.exe` запускается на чистой Windows (без Python) и работает в обоих режимах.
2. Тема переключается (Системная / Тёмная / Светлая) в настройках без перезапуска;
   GUI и Blockly выглядят согласованно; при режиме «Системная» приложение
   следует за темой Windows на лету.
3. Хоткеи старта/стопа/захвата точки редактируются в диалоге настроек,
   сохраняются в `%APPDATA%\ClicKit\settings.json`, применяются без перезапуска;
   конфликты и некорректные сочетания не принимаются.
4. Все ошибки уровня приложения попадают в лог-файл, пользователь видит
   понятное сообщение, консольный вывод в UTF-8 (без кракозябр).
5. `pytest` зелёный, `ruff check .` / `ruff format --check .` чистые.
6. README содержит инструкцию сборки и статус релиза 1.0.0.

## 2. Согласованные параметры (решения пользователя)

- **Тема:** режимы `system` / `dark` / `light`, по умолчанию `system`.
  Системная тема определяется `QStyleHints.colorScheme()`; реакция на смену
  темы Windows — сигнал `colorSchemeChanged`.
- **Язык:** в M5 только русский. Полноценная локализация RU+EN — backlog
  (Qt `tr` + строки JS + сообщения ядра — отдельная веха).
- **Хоткеи:** редактируются в диалоге настроек с записью нажатия; три
  действия: старт, стоп, захват точки. Перезапуск слушателя без рестарта
  приложения.
- **Версия:** 1.0.0 — первый публичный релиз (README, `APP_VERSION`, свойства exe).
- **Бэкенд ввода:** остаётся единственный pyautogui (ADR №7), выбор бэкенда
  в UI не выводится.
- **Упаковка:** PyInstaller; релиз 1.0.0 содержит оба варианта —
  `ClicKit-win64.zip` (onedir, старт ~2 с, рекомендуется) и `ClicKit.exe`
  (onefile, один файл, но распаковка ~220 МБ при каждом запуске). `resources/`
  целиком (включая Blockly, `msg/`, `media/`) в `datas`; рядом — NOTICE.

## 3. Модули и интерфейсы

### 3.1. Тема — `gui/theme.py`

```python
ThemeMode = Literal["system", "dark", "light"]
ALLOWED_THEMES: tuple[str, ...] = ("system", "dark", "light")


def resolve_theme(mode: str, system_is_dark: bool) -> Literal["dark", "light"]: ...
def stylesheet_for(theme: Literal["dark", "light"]) -> str: ...  # читает .qss


class ThemeManager(QObject):
    changed = Signal(str)  # разрешённая тема: "dark" | "light"

    def __init__(self, mode: str, parent: QObject | None = None) -> None: ...
    @property
    def mode(self) -> str: ...
    @property
    def effective(self) -> str: ...
    def apply(self, app: QApplication) -> None: ...  # setStyleSheet + сигнал
    def set_mode(self, mode: str) -> None: ...
```

- `resolve_theme` — чистая функция (тестируется без Qt).
- `ThemeManager` подписан на `QGuiApplication.styleHints().colorSchemeChanged`
  и переприменяет тему только в режиме `system`.
- Новые файлы: `resources/styles/light.qss` (светлая палитра, тот же набор
  селекторов, что в `dark.qss`), `resources/blockly/theme.js` — тема
  `clickitLight`, `editor.css` — переменные под `body[data-theme="light"]`.
- Blockly переключается через `editorApi.setTheme("dark"|"light")`:
  `workspace.setTheme(...)` + `document.body.dataset.theme`; вызов из Python —
  `EditorView.set_theme()`, применяется после `loadFinished` и при смене темы.
- Настройка: `Settings.theme` (`"system"` по умолчанию), `SETTINGS_VERSION = 2`;
  неизвестное значение → `"system"` (совместимость с v1: поле отсутствует).

### 3.2. Хоткеи и диалог настроек

- `gui/hotkey_spec.py` — чистые функции без Qt-виджетов:
  ```python
  def sequence_to_spec(sequence: str) -> str | None   # "Ctrl+Alt+S" → "<ctrl>+<alt>+s"
  def spec_to_text(spec: str) -> str                  # "<f5>" → "F5", "<ctrl>+a" → "Ctrl+A"
  def normalize_spec(spec: str) -> str                # нижний регистр, порядок модификаторов
  def validate_specs(specs: Mapping[str, str]) -> list[str]  # конфликты/пустые
  ```
  Поддерживаемые модификаторы: Ctrl, Alt, Shift, Win (Meta). Одиночные
  модификаторы и `Esc`/`Tab`/`Enter` как глобальные хоткеи запрещены —
  иначе они блокируют обычную работу.
- `gui/widgets/hotkey_edit.py` — `HotkeyEdit(QKeySequenceEdit)`: захват
  сочетания, отображение в понятном виде, `spec()` / `set_spec()`, сигнал
  `spec_changed(str)`.
- `gui/settings_dialog.py` — `SettingsDialog(QDialog)`:
  - тема (комбо: Системная / Тёмная / Светлая);
  - три поля хоткеев + подсказка «нажмите сочетание»;
  - кнопка «Сбросить к F5/F6/F8»;
  - OK/Отмена (`QDialogButtonBox`), валидация при OK: пустые, дубли,
    запрещённые сочетания — сообщение и фокус на проблемном поле;
  - результат: `settings` (копия) + `theme_changed`/`hotkeys_changed`.
- `core/hotkeys.py`: `HotkeyManager.reload(bindings)` — остановить слушатель,
  заменить привязки, запустить заново (потокобезопасно, идемпотентно).
- `gui/hotkey_bridge.py`: `HotkeyBridge.reload(settings)`.
- `gui/main_window.py`:
  - меню «Настройки → Параметры…» (`Ctrl+,`) и «Открыть папку логов»;
  - после диалога: сохранить настройки, применить тему, перезагрузить
    хоткеи, обновить подсказки в статус-баре и на кнопках;
  - `SimpleModeView.set_hotkeys(start, stop, pick)` — тексты кнопок
    «Старт (F5)», «Захватить точку (F8)»;
  - в JS — сигнал моста `hotkeys_changed(str, str)` для title кнопок
    «Запустить/Остановить» (F5/F6).
- Хоткеи по умолчанию остаются `F5`/`F6`/`F8`; аварийный стоп обязан быть
  назначен всегда (пустой стоп не принимается).

### 3.3. Логи и дружелюбные ошибки — `app/logging_setup.py`

- `log_dir() -> Path` — `%APPDATA%\ClicKit\logs`.
- `setup_logging(level=INFO) -> Path`:
  - `RotatingFileHandler` (`app.log`, 1 МБ × 3, UTF-8);
  - консольный `StreamHandler` с `errors="replace"` и UTF-8 (Windows `cmd`);
  - формат: время, уровень, модуль, сообщение;
  - возвращает путь к логу для меню/подсказки.
- `install_excepthook()`: `sys.excepthook` + `threading.excepthook` пишут
  `CRITICAL` с traceback; в GUI-потоке — понятный `QMessageBox` с путём к логу
  и советом перезапустить; приложение не «молчит».
- `app/application.py`: логирование до `QApplication`, `APP_VERSION = "1.0.0"`,
  применение темы из настроек, передача `ThemeManager` в окно.
- Дружелюбные сообщения: проверить, что ошибки сценария/файлов/настроек
  не показывают traceback (уже сделано в M3/M4) — добавить недостающие
  обёртки, если найдутся при ревью.

### 3.4. Упаковка — `packaging/`

- `resources/icons/app.ico` — генерируется `scripts/make_icon.py`
  (рендер SVG/вектора в PNG-размеры 16/32/48/64/128/256 и сборка ICO-контейнера
  с PNG-записями). Скрипт детерминированный, зависимостей нет.
- `packaging/ClicKit.spec` — onefile/onedir по `CLICKIT_ONEFILE`, windowed,
  иконка, `datas`: `resources/blockly` (рекурсивно, с `msg/` и `media/`),
  `resources/styles`, `resources/icons`, `resources/examples`; hidden imports
  QtWebEngine.
- `packaging/version_info.txt` — VSVersionInfo для свойств `.exe` (1.0.0).
- `packaging/NOTICE.txt` — LGPL v3 (Qt/PySide6, pynput), Apache-2.0 (Blockly),
  BSD-3-Clause (pyautogui); копируется рядом с `.exe` / в папку onedir.
- `scripts/build_exe.py` — `--onefile`, `--zip`, `--both` (релиз): чистит
  `build/`, собирает, копирует NOTICE, печатает путь; zip кладётся в `dist/`.
- `requirements-build.txt` — `pyinstaller>=6.10`.
- `.gitignore`: `build/`, `dist/`, `*.spec` — нет, spec наш (в `packaging/`),
  поэтому игнорируем только `build/` и `dist/` (проверить существующие правила).

### 3.5. Тесты

- `tests/test_theme.py` — `resolve_theme` (все режимы), `stylesheet_for`
  находит файл, `ThemeManager` переключает тему offscreen.
- `tests/test_hotkey_spec.py` — конверсия Qt ↔ pynput, нормализация,
  конфликты, запрещённые одиночные модификаторы.
- `tests/test_settings_dialog.py` — смоук: заполнение из настроек, валидация
  дублей, сброс к дефолтам, применение.
- `tests/test_hotkeys.py` — `HotkeyManager.reload` (без реального listener:
  подмена `keyboard.GlobalHotKeys`).
- `tests/test_logging.py` — файл создаётся, запись UTF-8, ротация настроена,
  excepthook пишет CRITICAL.
- Обновить `tests/test_settings.py` (поле `theme`, версия 2),
  `tests/test_gui_smoke.py` (меню и применение настроек).

## 4. ADR (дополнение к `AI_CONTEXT.md` §3.3)

- **ADR №25. Тема — единый источник разрешённой темы.** Настройка хранит
  режим (`system`/`dark`/`light`), а `ThemeManager` — единственное место,
  где режим превращается в конкретную тему. GUI (QSS) и Blockly получают
  уже разрешённое значение, поэтому рассинхрона «тёмное окно, светлый холст»
  не бывает.
- **ADR №26. Хоткей — строка pynput, UI-представление отдельно.** В настройках
  и ядре живёт спецификация pynput (`<ctrl>+<alt>+s`), в UI — человекочитаемый
  текст (`Ctrl+Alt+S`); конверсия — чистые функции в `gui/hotkey_spec.py`,
  покрытые тестами. Смена хоткеев не требует перезапуска приложения.
- **ADR №27. Логи — файл в `%APPDATA%\ClicKit\logs`.** Ротация 1 МБ × 3,
  UTF-8; путь к логу показывается в диалоге ошибки и доступен из меню.
  Пользовательские данные (настройки, логи, сценарии) не попадают в репозиторий.
- **ADR №28. Сборка — PyInstaller onefile + NOTICE рядом.** `resources/blockly`
  включается целиком; вендоренный Blockly не редактируется; NOTICE о LGPL/Apache
  кладётся в `dist/` рядом с `.exe` (требование лицензий, ADR №6).
- **ADR №29. Язык в M5 — только русский.** Локализация RU+EN — отдельная
  задача: требует инфраструктуры `QTranslator` и перевода JS/ядра; смешивать
  это с полировкой и упаковкой нецелесообразно.

## 5. Коммиты (по одному на фичу)

1. `feat: тема оформления — системная, тёмная и светлая`
   (`gui/theme.py`, `light.qss`, Blockly light-тема, `Settings.theme`,
   `EditorView.set_theme`, тесты).
2. `feat: диалог настроек — тема и глобальные хоткеи`
   (`hotkey_spec.py`, `HotkeyEdit`, `SettingsDialog`, меню, `reload`,
   динамические подсказки, тесты).
3. `feat: логи в файл и дружелюбные ошибки`
   (`app/logging_setup.py`, excepthook, меню «Открыть папку логов», тесты).
4. `feat: упаковка PyInstaller — иконка, ресурсы, NOTICE`
   (`packaging/`, `scripts/make_icon.py`, `scripts/build_exe.py`,
   `requirements-build.txt`, `.gitignore`).
5. `docs: M5 — релиз 1.0.0` (README, AI_CONTEXT, PROGRESS, ROADMAP).

## 6. Чек-лист приёмки

- [ ] `python -m app` — окно открывается в теме, соответствующей настройке.
- [ ] Смена темы Windows при «Системная» меняет GUI и Blockly на лету.
- [ ] Переключение тёмная/светлая в настройках — без перезапуска, Blockly
      сохраняет собранный сценарий и позиции блоков.
- [ ] Хоткеи: запись сочетания, сохранение, применение без перезапуска,
      конфликт/пустой стоп отклоняются, сброс к F5/F6/F8.
- [ ] `%APPDATA%\ClicKit\logs\app.log` пишется, ротация работает.
- [ ] **Обе сборки:** onedir-архив и `.exe` — два режима, редактор Blockly
      (палитра, сохранение/открытие), иконка в проводнике/панели задач,
      NOTICE рядом; onedir стартует за секунды, onefile — дольше (распаковка).
- [ ] `ruff check .`, `ruff format --check .`, `pytest` — чисто.
