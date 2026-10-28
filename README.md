<div align="center">

# 🧰 ClicKit

**The auto-clicker that builds like a kit.**

A Windows auto-clicker with visual block scripting: snap colorful blocks
together to script clicks, moves and delays — no coding required.

[![Windows](https://img.shields.io/badge/OS-Windows_10%2F11-0078D6?logo=windows&logoColor=white)](https://www.microsoft.com/windows)
[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org)
[![PySide6](https://img.shields.io/badge/GUI-PySide6_%2B_Qt-41CD52?logo=qt&logoColor=white)](https://doc.qt.io/qtforpython/)
[![Blockly](https://img.shields.io/badge/scripting-Blockly-4285F4?logo=googleblockly&logoColor=white)](https://developers.google.com/blockly)
[![Status](https://img.shields.io/badge/status-1.0.0_release_candidate-5865F2)](#)

**English** · [Русский](#ru)

</div>

---

<a id="en"></a>

## 🚧 Project status

**ClicKit 1.0.0** — the first public release. Milestones **M0–M5** are complete
and merged into `master`. The app follows the Windows theme by default
(system / dark / light can be picked in Settings), all three global hotkeys
(start, stop, coordinate picker) are configurable without a restart, and a
rotated log is written to `%APPDATA%\ClicKit\logs\app.log`. Two modes are
available: the classic **Simple mode** and the **block scenario editor** with
live execution highlighting. The release ships as a single `ClicKit.exe` built
with PyInstaller, so no Python installation is required. Conditions
(`if`/`while`) and the input recorder remain on the roadmap.

## 💡 Why ClicKit?

Regular auto-clickers can only spam one spot on the screen. Advanced macro
tools can do much more, but their interfaces overwhelm people who simply
want to automate a few clicks.

**ClicKit sits in the sweet spot between the two:**

| Mode | Who it is for |
|---|---|
| 🖱️ **Simple mode** | A classic auto-clicker: pick a spot on screen, set interval, mouse button and repeat count — done. |
| 🧩 **Scenario mode** | A visual editor based on Blockly: build complex sequences from drag-and-drop blocks — clicks, moves, delays, loops, conditions — like snapping LEGO bricks. |

## ✨ Key features

- ✅ 🎯 **Coordinate picker** — hover the mouse and press the picker hotkey (`F8` by default) to capture the point;
- ✅ ⛑️ **Global emergency stop** (`F6` by default) — works from any application, even if a script is stuck in a loop;
- ✅ ⌨️ **Configurable hotkeys** — start, stop and picker keys can be re-recorded in Settings and apply instantly;
- ✅ 🧩 **Block editor** with a friendly Russian palette — scenarios are assembled visually, no text code (conditions are planned for a later release);
- ✅ 💾 **Scenarios as safe data files** (`.acl.json`) — validated, versioned internal format (IR); no arbitrary code is ever executed;
- ✅ ▶️ **Live execution highlighting** — the editor shows which block is running right now;
- ✅ 🌗 **System, dark and light themes** — GUI and Blockly switch together, following Windows in system mode;
- ✅ 🪵 **Logs and clear errors** — rotated UTF-8 log in `%APPDATA%\ClicKit\logs`, friendly crash dialog;
- ✅ 📦 **Two release builds** — a fast portable folder (`ClicKit-win64.zip`) and a single-file `.exe` for when one file matters; neither needs Python installed.

## 🗺️ Roadmap

| Milestone | Goal | Status |
|---|---|---|
| **M0** | Repository skeleton: structure, dependencies, app entry point | ✅ Done |
| **M1** | Click engine (core): input backends, global hotkeys, executor — no GUI | ✅ Done |
| **M2** | Main window + Simple mode (MVP auto-clicker) | ✅ Done |
| **M3** | Scenario model (IR): schema, interpreter, save / load | ✅ Done |
| **M4** | Blockly visual editor with live execution | ✅ Done |
| **M5** | Polish: themes, settings, logs, tests, `.exe` packaging | ✅ Done |

Details: [`ROADMAP.md`](ROADMAP.md).

## 🚀 Getting started

**Release builds** (Windows 10/11, no Python needed):

- `ClicKit-win64.zip` — **recommended**: unpack the folder and run
  `ClicKit\ClicKit.exe`; starts in a couple of seconds.
- `ClicKit.exe` — a single portable file. QtWebEngine (~220 MB) unpacks itself
  on every launch, so the window may take up to a minute to appear.

Keep `NOTICE.txt` next to the executable. Settings and logs live in
`%APPDATA%\ClicKit`.

**Run from source:**

```bash
git clone https://github.com/AkaDaka1/ClicKit.git
cd ClicKit
pip install -r requirements.txt
python -m app
```

**Build the release artifacts:**

```bash
pip install -r requirements-build.txt
python scripts/build_exe.py --both   # zip + single .exe
```

Results: `dist/ClicKit-win64.zip` (folder build, fast start),
`dist/ClicKit.exe` (single file), and `NOTICE.txt` beside/in the build.
`--zip` builds only the folder archive, `--onefile` only the single file.
The `resources/` tree — including the vendored Blockly — is packed into both.

**Simple mode in four steps:**

1. Set the click point: type X/Y, or hover the cursor over the target and press
   `F8` (the "Current position" button captures it instantly).
2. Pick the mouse button, the interval in milliseconds and the number of
   repeats — or tick "Infinite".
3. Press **Start** or `F5`. Stop at any time with `F6` — it works from any
   application, even when ClicKit is hidden in the tray.
4. Closing the window asks whether to minimize to tray or exit; tick
   "Remember my choice" to skip the question for that case next time.

Settings (theme, global hotkeys, click parameters) live in
`%APPDATA%\ClicKit\settings.json`; **Settings → Parameters…** (`Ctrl+,`) changes
the theme and hotkeys without a restart. Logs are in
`%APPDATA%\ClicKit\logs\app.log` (**Help → Open log folder**). Moving the cursor
to a screen corner also triggers the pyautogui fail-safe stop.

**Scenario editor (M4):**

1. Open the **Scenario editor** tab. The starter scenario shows the idea:
   click → pause → repeat 3×(move + click).
2. Drag blocks from the palette (Mouse, Keyboard, Delays, Loops) and type
   coordinates and durations directly in the blocks.
3. Press **Run** or `F5`: on the editor tab `F5` runs the scenario, on Simple
   mode it starts clicks. `F6` stops either one from any application.
4. The running block is highlighted. Invalid blocks (for example, an empty
   loop) get a warning and the scenario is not executed. `Ctrl+S` / `Ctrl+O`
   save and open `.acl.json`; undo/redo live in the toolbar.

Saved files stay regular IR scenarios (usable by `scripts/run_scenario.py`)
and additionally keep the canvas state in `editor.workspace`. Blockly is
vendored locally, so the editor works without internet access.

**Click engine demo (M1, console):**

```bash
python scripts/demo_click.py --x 1000 --y 500 --count 100 --interval 0.1
```

`F5` starts clicking, `F6` stops instantly from any application, `Esc` exits.

**Scenario runner (M3, console):**

```bash
python scripts/run_scenario.py resources/examples/click_pause_loop.acl.json
python scripts/run_scenario.py my-scenario.acl.json --dry-run
```

`F6` stops, `Esc` exits. `--dry-run` validates the scenario and prints the
action count without touching the mouse. Scenario files use the versioned,
validated ClicKit IR format (`.acl.json`); node types: `click`, `double_click`,
`move`, `drag`, `delay`, `key`, `scroll`, `loop`, `sequence`.

**Requirements:** Windows 10/11. The release `.exe` needs no Python; running
from source or building requires Python 3.11+.

## 🛠️ Tech stack

Python 3.11+ · PySide6 (Qt for Python, LGPL) · Blockly (vendored, Apache-2.0)
inside `QWebEngineView` · `QWebChannel` JS↔Python bridge · `pyautogui` + `pynput`
behind a pluggable `InputBackend` abstraction · PyInstaller for packaging.

- Architecture and coding rules: [`AI_CONTEXT.md`](AI_CONTEXT.md)
- Work log: [`PROGRESS.md`](PROGRESS.md)

## ⚠️ Disclaimer

ClicKit is intended for offline and non-commercial use: automating routine
tasks, testing your own software, single-player games. Using auto-clickers in
online games with anti-cheat protection may violate their terms of service —
you alone are responsible for how you use this tool.

## 📄 License

Released under the [MIT License](LICENSE) © 2026 Danil Momot. Third-party
components keep their own licenses: PySide6 — LGPL v3, Blockly — Apache-2.0.

---

<a id="ru"></a>

<div align="center">

# 🧰 ClicKit (Русский)

**Автокликер, который собирается как конструктор.**

Автокликер для Windows с визуальным блочным программированием: соединяйте
цветные блоки, чтобы собрать сценарий кликов, перемещений и задержек —
без единой строчки кода.

[English](#en) · **Русский**

</div>

## 🚧 Статус проекта

**ClicKit 1.0.0** — первый публичный релиз. Вехи **M0–M5** завершены и влиты
в `master`. По умолчанию приложение следует теме Windows (в настройках можно
выбрать «Системная», «Тёмная» или «Светлая»), все три глобальных хоткея
(старт, стоп, захват точки) переназначаются без перезапуска, а журнал
с ротацией пишется в `%APPDATA%\ClicKit\logs\app.log`. Доступны два режима:
классический **«Простой режим»** и **блочный редактор сценариев** с подсветкой
выполнения. Релиз поставляется одним файлом `ClicKit.exe`, собранным через
PyInstaller, — Python на целевой машине не нужен. Условия (`if`/`while`)
и запись действий остаются в планах.

## 💡 Почему ClicKit?

Обычные автокликеры умеют лишь спамить кликами в одной точке экрана.
Продвинутые макрос-инструменты способны на большее, но их интерфейсы
пугают тех, кому нужно просто автоматизировать пару кликов.

**ClicKit — золотая середина:**

| Режим | Для кого |
|---|---|
| 🖱️ **Простой режим** | Классический автокликер: выбрал точку на экране, задал интервал, кнопку мыши и число повторов — готово. |
| 🧩 **Режим сценариев** | Визуальный редактор на базе Blockly: сложные последовательности собираются перетаскиванием блоков — клики, движения, задержки, циклы, условия — как детали LEGO. |

## ✨ Ключевые возможности

- ✅ 🎯 **Пикер координат** — наведи мышь и нажми хоткей захвата (`F8` по умолчанию), точка захвачена;
- ✅ ⛑️ **Глобальный аварийный стоп** (`F6` по умолчанию) — срабатывает из любого приложения, даже если сценарий «завис» в цикле;
- ✅ ⌨️ **Настраиваемые хоткеи** — старт, стоп и захват точки переназначаются в настройках и применяются сразу;
- ✅ 🧩 **Редактор блоков** с понятной палитрой на русском — сценарии собираются визуально, без текстового кода (условия — в следующих версиях);
- ✅ 💾 **Сценарии — это безопасные файлы данных** (`.acl.json`): валидируемый версионируемый формат (IR), произвольный код никогда не исполняется;
- ✅ ▶️ **Подсветка выполнения** — редактор показывает, какой блок исполняется прямо сейчас;
- ✅ 🌗 **Системная, тёмная и светлая темы** — GUI и Blockly переключаются вместе, в системном режиме следуют за Windows;
- ✅ 🪵 **Журналы и понятные ошибки** — UTF-8-журнал с ротацией в `%APPDATA%\ClicKit\logs`, дружелюбный диалог при сбое;
- ✅ 📦 **Две сборки** — быстрая переносимая папка (`ClicKit-win64.zip`) и один `.exe` для случаев, когда важен единственный файл; Python не нужен ни там, ни там.

## 🗺️ Дорожная карта

| Веха | Цель | Статус |
|---|---|---|
| **M0** | Скелет репозитория: структура, зависимости, точка входа | ✅ Готово |
| **M1** | Движок кликов (core): бэкенды ввода, глобальные хоткеи, исполнитель — без GUI | ✅ Готово |
| **M2** | Главное окно + Простой режим (MVP-автокликер) | ✅ Готово |
| **M3** | Модель сценариев (IR): схема, интерпретатор, сохранение / загрузка | ✅ Готово |
| **M4** | Визуальный редактор Blockly с подсветкой выполнения | ✅ Готово |
| **M5** | Полировка: темы, настройки, журналы, тесты, упаковка в `.exe` | ✅ Готово |

Подробнее: [`ROADMAP.md`](ROADMAP.md).

## 🚀 Быстрый старт

**Готовые сборки** (Windows 10/11, Python не нужен):

- `ClicKit-win64.zip` — **рекомендуется**: распакуйте папку и запустите
  `ClicKit\ClicKit.exe`; старт за пару секунд.
- `ClicKit.exe` — один переносимый файл. QtWebEngine (~220 МБ) распаковывается
  при каждом запуске, поэтому окно может появиться до минуты.

`NOTICE.txt` держите рядом с исполняемым файлом. Настройки и журналы — в
`%APPDATA%\ClicKit`.

**Запуск из исходников:**

```bash
git clone https://github.com/AkaDaka1/ClicKit.git
cd ClicKit
pip install -r requirements.txt
python -m app
```

**Сборка артефактов релиза:**

```bash
pip install -r requirements-build.txt
python scripts/build_exe.py --both   # zip + один .exe
```

Результат: `dist/ClicKit-win64.zip` (папка, быстрый старт),
`dist/ClicKit.exe` (один файл) и `NOTICE.txt` рядом/внутри. `--zip` собирает
только архив папки, `--onefile` — только один файл. Каталог `resources/`
вместе с вендоренным Blockly упаковывается в обе сборки.

**Простой режим — четыре шага:**

1. Задайте точку клика: введите X/Y или наведите мышь на цель и нажмите `F8`
   (кнопка «Текущая позиция» берёт координаты мгновенно).
2. Выберите кнопку мыши, интервал в миллисекундах и число повторов — или
   отметьте «Бесконечно».
3. Нажмите **Старт** или `F5`. Остановить можно в любой момент по `F6` — это
   работает из любого приложения, даже если ClicKit свёрнут в трей.
4. При закрытии окна ClicKit спросит, свернуть его в трей или выйти; галочка
   «Запомнить мой выбор» избавит от вопроса для этого случая.

Настройки (тема, глобальные хоткеи, параметры кликов) хранятся в
`%APPDATA%\ClicKit\settings.json`; **«Настройки → Параметры…»** (`Ctrl+,`)
меняет тему и хоткеи без перезапуска. Журналы — в
`%APPDATA%\ClicKit\logs\app.log` (**«Помощь → Открыть папку журналов»**).
Курсор в углу экрана также срабатывает как аварийный стоп pyautogui (fail-safe).

**Редактор сценариев (M4):**

1. Откройте вкладку **«Редактор сценариев»**. Стартовый пример показывает
   идею: клик → пауза → цикл 3×(движение + клик).
2. Перетаскивайте блоки из палитры (Мышь, Клавиатура, Задержки, Циклы) и
   вводите координаты и задержки прямо в блоках.
3. Нажмите **Запустить** или `F5`: на вкладке редактора `F5` запускает
   сценарий, в «Простом режиме» — клики. `F6` останавливает и то, и другое
   из любого приложения.
4. Выполняемый блок подсвечивается. Ошибочные блоки (например, пустое тело
   цикла) получают предупреждение, а сценарий не запускается. `Ctrl+S` /
   `Ctrl+O` сохраняют и открывают `.acl.json`; отмена и повтор — в тулбаре.

Сохранённые файлы остаются обычными IR-сценариями (их понимает
`scripts/run_scenario.py`) и дополнительно хранят состояние холста в
`editor.workspace`. Blockly вендорен локально — редактор работает без
интернета.

**Консольное демо движка кликов (M1):**

```bash
python scripts/demo_click.py --x 1000 --y 500 --count 100 --interval 0.1
```

`F5` — старт кликов, `F6` — мгновенный стоп из любого приложения, `Esc` — выход.

**Консольный запуск сценария (M3):**

```bash
python scripts/run_scenario.py resources/examples/click_pause_loop.acl.json
python scripts/run_scenario.py my-scenario.acl.json --dry-run
```

`F6` — стоп, `Esc` — выход. `--dry-run` проверяет сценарий и печатает число
действий, не трогая мышь. Файлы сценариев — версионированный и валидируемый
формат IR (`.acl.json`); типы узлов: `click`, `double_click`, `move`, `drag`,
`delay`, `key`, `scroll`, `loop`, `sequence`.

**Требования:** Windows 10/11. Готовому `.exe` Python не нужен; для запуска
из исходников и сборки — Python 3.11+.

## 🛠️ Технологии

Python 3.11+ · PySide6 (Qt for Python, LGPL) · Blockly (vendored, Apache-2.0)
внутри `QWebEngineView` · мост JS↔Python на `QWebChannel` · `pyautogui` + `pynput`
за сменной абстракцией `InputBackend` · упаковка через PyInstaller.

- Архитектура и правила кодинга: [`AI_CONTEXT.md`](AI_CONTEXT.md)
- Журнал работ: [`PROGRESS.md`](PROGRESS.md)

## ⚠️ Дисклеймер

ClicKit предназначен для некоммерческого и офлайн-использования: автоматизация
рутинных задач, тестирование собственного ПО, одиночные игры. Использование
автокликеров в онлайн-играх с античит-защитой может нарушать их правила —
ответственность за применение инструмента несёте только вы.

## 📄 Лицензия

Проект распространяется по лицензии [MIT](LICENSE) © 2026 Danil Momot.
Сторонние компоненты сохраняют свои лицензии: PySide6 — LGPL v3,
Blockly — Apache-2.0.
