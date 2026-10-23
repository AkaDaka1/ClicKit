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

ClicKit is in early development. Right now the repository contains the
project blueprint — context, roadmap and progress log — and the application
skeleton is being built (milestone **M0**). There are no releases yet;
this README will grow screenshots and install instructions as milestones land.

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
- 🌗 **Dark / light themes**, system tray icon, configurable hotkeys;
- 📦 **Single `.exe`** — runs on a clean Windows without Python installed.

## 🗺️ Roadmap

| Milestone | Goal | Status |
|---|---|---|
| **M0** | Repository skeleton: structure, dependencies, app entry point | 🚧 In progress |
| **M1** | Click engine (core): input backends, global hotkeys, executor — no GUI | ⬜ Planned |
| **M2** | Main window + Simple mode (MVP auto-clicker) | ⬜ Planned |
| **M3** | Scenario model (IR): schema, interpreter, save / load | ⬜ Planned |
| **M4** | Blockly visual editor with live execution | ⬜ Planned |
| **M5** | Polish: themes, settings, tests, `.exe` packaging | ⬜ Planned |

Details: [`ROADMAP.md`](ROADMAP.md).

## 🚀 Getting started

> The application code is not in the repository yet — the instructions below
> become valid once milestone M0 is complete.

```bash
git clone https://github.com/<owner>/ClicKit.git
cd ClicKit
pip install -r requirements.txt
python -m app
```

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

ClicKit находится на ранней стадии разработки. Сейчас в репозитории —
«чертёж» проекта: контекст, дорожная карта и журнал прогресса, — а также
создаётся скелет приложения (веха **M0**). Релизов пока нет; по мере
выполнения вех в этом README появятся скриншоты и инструкции по установке.

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
- 🌗 **Тёмная / светлая темы**, иконка в системном трее, настраиваемые хоткеи;
- 📦 **Один `.exe`-файл** — работает на чистой Windows без установленного Python.

## 🗺️ Дорожная карта

| Веха | Цель | Статус |
|---|---|---|
| **M0** | Скелет репозитория: структура, зависимости, точка входа | 🚧 В работе |
| **M1** | Движок кликов (core): бэкенды ввода, глобальные хоткеи, исполнитель — без GUI | ⬜ Запланировано |
| **M2** | Главное окно + Простой режим (MVP-автокликер) | ⬜ Запланировано |
| **M3** | Модель сценариев (IR): схема, интерпретатор, сохранение / загрузка | ⬜ Запланировано |
| **M4** | Визуальный редактор Blockly с подсветкой выполнения | ⬜ Запланировано |
| **M5** | Полировка: темы, настройки, тесты, упаковка в `.exe` | ⬜ Запланировано |

Подробнее: [`ROADMAP.md`](ROADMAP.md).

## 🚀 Быстрый старт

> Кода приложения в репозитории ещё нет — инструкция ниже заработает
> после завершения вехи M0.

```bash
git clone https://github.com/<owner>/ClicKit.git
cd ClicKit
pip install -r requirements.txt
python -m app
```

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
