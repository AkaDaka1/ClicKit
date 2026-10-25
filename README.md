<div align="center">

# 🧰 ClicKit

**The auto-clicker that builds like a kit.**

A Windows auto-clicker with visual block scripting: snap colorful blocks
together to script clicks, moves and delays — no coding required.

[![Windows](https://img.shields.io/badge/OS-Windows_10%2F11-0078D6?logo=windows&logoColor=white)](https://www.microsoft.com/windows)
[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org)
[![PySide6](https://img.shields.io/badge/GUI-PySide6_%2B_Qt-41CD52?logo=qt&logoColor=white)](https://doc.qt.io/qtforpython/)
[![Blockly](https://img.shields.io/badge/scripting-Blockly-4285F4?logo=googleblockly&logoColor=white)](https://developers.google.com/blockly)
![Status](https://img.shields.io/badge/status-in_development-FFA500)

**English** · [Русский](#ru)

</div>

---

<a id="en"></a>

## 🚧 Project status

ClicKit is in active development. The repository skeleton (**M0**), the click
engine core (**M1**) and the first user-facing milestone (**M2**) are done:
a dark-themed main window with two modes, a ready-to-use Simple mode
(coordinate picker on `F8`, interval in milliseconds, repeat count or infinite
mode, start/stop by button and global hotkeys), a system tray icon and settings
persisted to `%APPDATA%\ClicKit\settings.json`. M2 is in manual review; there
are no public releases yet. Screenshots and detailed install instructions will
appear as milestones land.

## 💡 Why ClicKit?

Regular auto-clickers can only spam one spot on the screen. Advanced macro
tools can do much more, but their interfaces overwhelm people who simply
want to automate a few clicks.

**ClicKit sits in the sweet spot between the two:**

| Mode | Who it is for |
|---|---|
| 🖱️ **Simple mode** | A classic auto-clicker: pick a spot on screen, set interval, mouse button and repeat count — done. |
| 🧩 **Scenario mode** | A visual editor based on Blockly: build complex sequences from drag-and-drop blocks — clicks, moves, delays, loops, conditions — like snapping LEGO bricks. |

## ✨ Planned features

- 🎯 **Coordinate picker** — hover the mouse and press `F8` to capture the point;
- ⛑️ **Global emergency stop** (`F6`) — works from any application, even if a script is stuck in a loop;
- 🧩 **Block editor** with a friendly palette — scenarios are assembled visually, no text code;
- 💾 **Scenarios as safe data files** (`.acl.json`) — validated, versioned internal format (IR); no arbitrary code is ever executed;
- ▶️ **Live execution highlighting** — the editor shows which block is running right now;
- 🌗 **Dark theme** with a system tray icon; the light theme and configurable hotkeys are planned;
- 📦 **Single `.exe`** — runs on a clean Windows without Python installed.

## 🗺️ Roadmap

| Milestone | Goal | Status |
|---|---|---|
| **M0** | Repository skeleton: structure, dependencies, app entry point | ✅ Done |
| **M1** | Click engine (core): input backends, global hotkeys, executor — no GUI | ✅ Done |
| **M2** | Main window + Simple mode (MVP auto-clicker) | 🟡 Implemented, in review |
| **M3** | Scenario model (IR): schema, interpreter, save / load | ⬜ Planned |
| **M4** | Blockly visual editor with live execution | ⬜ Planned |
| **M5** | Polish: themes, settings, tests, `.exe` packaging | ⬜ Planned |

Details: [`ROADMAP.md`](ROADMAP.md).

## 🚀 Getting started

> ClicKit runs from source for now: `python -m app` opens the main window with
> the working Simple mode. The block editor tab is a placeholder until M4.

```bash
git clone https://github.com/AkaDaka1/ClicKit.git
cd ClicKit
pip install -r requirements.txt
python -m app
```

**Simple mode in four steps:**

1. Set the click point: type X/Y, or hover the cursor over the target and press
   `F8` (the "Current position" button captures it instantly).
2. Pick the mouse button, the interval in milliseconds and the number of
   repeats — or tick "Infinite".
3. Press **Start** or `F5`. Stop at any time with `F6` — it works from any
   application, even when ClicKit is hidden in the tray.
4. Closing the window asks whether to minimize to tray or exit; tick
   "Remember my choice" to skip the question for that case next time.

Settings live in `%APPDATA%\ClicKit\settings.json`. Moving the cursor to a
screen corner also triggers the pyautogui fail-safe stop.

**Click engine demo (M1, console):**

```bash
python scripts/demo_click.py --x 1000 --y 500 --count 100 --interval 0.1
```

`F5` starts clicking, `F6` stops instantly from any application, `Esc` exits.

**Requirements:** Windows 10/11, Python 3.11+.

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

ClicKit находится в активной разработке. Скелет репозитория (веха **M0**),
ядро движка кликов (**M1**) и первая пользовательская веха (**M2**) готовы:
тёмное главное окно с двумя режимами, рабочий «Простой режим» (пикер координат
по `F8`, интервал в миллисекундах, число повторов или «Бесконечно», старт/стоп
кнопкой и глобальными хоткеями), иконка в трее и настройки в
`%APPDATA%\ClicKit\settings.json`. M2 проходит ручную приёмку. Публичных
релизов пока нет; скриншоты и подробные инструкции по установке будут
добавляться по мере выполнения вех.

## 💡 Почему ClicKit?

Обычные автокликеры умеют лишь спамить кликами в одной точке экрана.
Продвинутые макрос-инструменты способны на большее, но их интерфейсы
пугают тех, кому нужно просто автоматизировать пару кликов.

**ClicKit — золотая середина:**

| Режим | Для кого |
|---|---|
| 🖱️ **Простой режим** | Классический автокликер: выбрал точку на экране, задал интервал, кнопку мыши и число повторов — готово. |
| 🧩 **Режим сценариев** | Визуальный редактор на базе Blockly: сложные последовательности собираются перетаскиванием блоков — клики, движения, задержки, циклы, условия — как детали LEGO. |

## ✨ Планируемые возможности

- 🎯 **Пикер координат** — наведи мышь и нажми `F8`, точка захвачена;
- ⛑️ **Глобальный аварийный стоп** (`F6`) — срабатывает из любого приложения, даже если сценарий «завис» в цикле;
- 🧩 **Редактор блоков** с понятной палитрой на русском — сценарии собираются визуально, без текстового кода;
- 💾 **Сценарии — это безопасные файлы данных** (`.acl.json`): валидируемый версионируемый формат (IR), произвольный код никогда не исполняется;
- ▶️ **Подсветка выполнения** — редактор показывает, какой блок исполняется прямо сейчас;
- 🌗 **Тёмная тема** и иконка в системном трее; светлая тема и настраиваемые хоткеи — в планах;
- 📦 **Один `.exe`-файл** — работает на чистой Windows без установленного Python.

## 🗺️ Дорожная карта

| Веха | Цель | Статус |
|---|---|---|
| **M0** | Скелет репозитория: структура, зависимости, точка входа | ✅ Готово |
| **M1** | Движок кликов (core): бэкенды ввода, глобальные хоткеи, исполнитель — без GUI | ✅ Готово |
| **M2** | Главное окно + Простой режим (MVP-автокликер) | 🟡 Реализовано, на приёмке |
| **M3** | Модель сценариев (IR): схема, интерпретатор, сохранение / загрузка | ⬜ Запланировано |
| **M4** | Визуальный редактор Blockly с подсветкой выполнения | ⬜ Запланировано |
| **M5** | Полировка: темы, настройки, тесты, упаковка в `.exe` | ⬜ Запланировано |

Подробнее: [`ROADMAP.md`](ROADMAP.md).

## 🚀 Быстрый старт

> Пока ClicKit запускается из исходников: `python -m app` открывает главное окно
> с рабочим «Простым режимом». Вкладка редактора — заглушка до вехи M4.

```bash
git clone https://github.com/AkaDaka1/ClicKit.git
cd ClicKit
pip install -r requirements.txt
python -m app
```

**Простой режим — четыре шага:**

1. Задайте точку клика: введите X/Y или наведите мышь на цель и нажмите `F8`
   (кнопка «Текущая позиция» берёт координаты мгновенно).
2. Выберите кнопку мыши, интервал в миллисекундах и число повторов — или
   отметьте «Бесконечно».
3. Нажмите **Старт** или `F5`. Остановить можно в любой момент по `F6` — это
   работает из любого приложения, даже если ClicKit свёрнут в трей.
4. При закрытии окна ClicKit спросит, свернуть его в трей или выйти; галочка
   «Запомнить мой выбор» избавит от вопроса для этого случая.

Настройки хранятся в `%APPDATA%\ClicKit\settings.json`. Курсор в углу экрана
также срабатывает как аварийный стоп pyautogui (fail-safe).

**Консольное демо движка кликов (M1):**

```bash
python scripts/demo_click.py --x 1000 --y 500 --count 100 --interval 0.1
```

`F5` — старт кликов, `F6` — мгновенный стоп из любого приложения, `Esc` — выход.

**Требования:** Windows 10/11, Python 3.11+.

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
