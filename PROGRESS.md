# PROGRESS.md — Лог прогресса проекта ClicKit

> Обновляется после каждой выполненной задачи. Формат записи:
> `ГГГГ-ММ-ДД — что сделано — результат/статус`.
> При изменении набора инструментов или появлении новых артефактов/генерируемых
> файлов — проверяй и дополняй `.gitignore` (правило зафиксировано в `AI_CONTEXT.md` §4).

---

## Журнал

| Дата | Задача | Статус |
|---|---|---|
| 2026-10-23 | Инициализация проекта: созданы `AI_CONTEXT.md`, `PROGRESS.md`, `ROADMAP.md`, зафиксированы стек и архитектура | ✅ Готово |
| 2026-10-23 | Создан `.gitignore` (Python, venv, тесты/линтеры, PyInstaller, логи, секреты, IDE, артефакты ОС); правило «держать `.gitignore` актуальным» внесено в `AI_CONTEXT.md` (шапка + §4) и в шапку `PROGRESS.md` | ✅ Готово |
| 2026-10-23 | Создан `AGENTS.md` — короткие стартовые инструкции для ИИ-агента (чтение AI_CONTEXT/PROGRESS/ROADMAP, правила обновления документации и `.gitignore`); файл добавлен в дерево структуры репозитория (`AI_CONTEXT.md` §3.2) | ✅ Готово |
| 2026-10-23 | Первый коммит в git (ветка `master`): документационный каркас проекта — 5 файлов | ✅ Готово |
| 2026-10-23 | Творческий этап: выбрано название продукта — **ClicKit** (проверено на GitHub: крупных тёзок нет); создан двуязычный `README.md` (EN + RU) со статусом, фичами, roadmap и дисклеймером; подготовлены описание и topics для GitHub-репозитория; `AI_CONTEXT.md` обновлён (название, ADR №5) | ✅ Готово |
| 2026-10-23 | Выбрана лицензия **MIT** (правообладатель: Danil Momot); создан файл `LICENSE` в корне; секции «License/Лицензия» в `README.md` заменены с «to be decided» на ссылку на MIT; `AI_CONTEXT.md` обновлён (ADR №6, `LICENSE` в структуре репозитория) | ✅ Готово |
| 2026-10-23 | Создана директория `plans/` для рабочих планов (gitignored); план M0 зафиксирован в `plans/M0-skeleton.md`; `.gitignore` дополнен, шапка исправлена AutoClicker → ClicKit | ✅ Готово |
| 2026-10-23 | **M0 завершён:** структура каталогов (`app/`, `core/`, `gui/`, `bridge/`, `resources/`, `tests/`), `requirements.txt` (PySide6>=6.7, pyautogui>=0.9, pynput>=1.7 + ruff/pytest), `pyproject.toml` (ruff: py311, line-length 88, E/F/W/I/UP/B), точка входа `python -m app` → пустое окно «ClicKit» 1024×680; секция «Команды» в `AGENTS.md` заполнена; проверено: `ruff check` — 0 ошибок, `python -m app` — окно открывается | ✅ Готово |
| 2026-10-24 | Процессы: зафиксировано правило планов вех — подробный план каждого этапа (M0, M1, ...) создаётся в `plans/` по запросу пользователя, перед работой по пункту читать план (`AGENTS.md`, секция «Планы вех»); ADR №7 — единый бэкенд отправки pyautogui (pynput — только глобальные слушатели), `pynput_backend.py` исключён из `AI_CONTEXT.md` §3.2; в §3.2 добавлены `plans/` и `scripts/`; подробный план M1 согласован и создан — `plans/M1-core-engine.md` (реализация — в новой сессии) | ✅ Готово |
| 2026-10-24 | **M1 реализован** в ветке `feat/m1-core-engine` (7 коммитов): `core/input/backend.py` (ABC `InputBackend`, `Button`, фабрика `create_backend`), `core/input/pyautogui_backend.py` (`PyAutoguiBackend`, FAILSAFE=True, PAUSE=0), `core/executor.py` (`Executor` в `threading.Thread` + `threading.Event`, прерываемый интервал, `on_step`), `core/hotkeys.py` (`HotkeyManager` на `pynput.GlobalHotKeys`), `tests/test_executor.py` (5 тестов с `MockBackend`), `scripts/demo_click.py`; `ruff check`/`format` — чисто, `pytest` — 5 passed | ✅ Готово |
| 2026-10-24 | **Ручная приёмка M1 пройдена:** демо `--count 100 --interval 0.1` — 100/100 кликов; F5 (старт), F6 (стоп из любого окна), Esc (выход), fail-safe (курсор в угол — стоп) работают; ветка `feat/m1-core-engine` влита в `master` | ✅ Готово |
| 2026-10-25 | Согласован план M2 (`plans/M2-gui-simple-mode.md`): интервал в мс, фиксированные хоткеи F5/F6/F8, тёмная тема, два диалога закрытия с «Запомнить выбор», настройки в `%APPDATA%`; идея «клики без захвата курсора» отложена в спайк после M2 (ADR №12) | ✅ Готово |
| 2026-10-25 | **M2 реализован** в ветке `feat/m2-gui-simple-mode`: `core/settings.py` (JSON в `%APPDATA%`, атомарная запись), `position()` и `FailsafeTriggered` в `InputBackend`, `StopReason`/`on_finish` в `Executor`, `gui/executor_adapter.py`, `gui/hotkey_bridge.py`, `gui/picker.py`, `gui/simple_mode/{config,view}.py`, `gui/main_window.py` (две вкладки, трей, диалоги закрытия), `gui/tray.py`, `gui/icons.py`, `app/paths.py`, тёмная тема `resources/styles/dark.qss`, иконка `resources/icons/app.svg`; `ruff check`/`format` — чисто, `pytest` — 35 passed | ✅ Ожидает ручной приёмки |

---

## Текущий статус

- **Этап:** **M2 реализован** (ветка `feat/m2-gui-simple-mode`) — ожидает ручной приёмки и слияния в `master`.
- **M0:** завершён — скелет проекта с рабочей точкой входа `python -m app`.
- **M1:** завершён и влит в `master` — движок кликов, глобальные хоткеи, консольное демо.
- **M2:** главное окно с двумя режимами, «Простой режим» (точка + пикер F8, кнопка мыши,
  интервал в мс, повторы/∞, старт-стоп кнопкой и F5/F6), тёмная тема, трей,
  настройки в `%APPDATA%\ClicKit\settings.json`, диалоги закрытия с «Запомнить выбор».
- **Название продукта:** **ClicKit** — «click it» + «kit» (конструктор); решение зафиксировано в `AI_CONTEXT.md` §3.3 (ADR №5).
- **Организационное:** папка переименована в `ClicKit`, GitHub-remote `origin` → `github.com/AkaDaka1/ClicKit` подключён.
- **Зависимости:** установлены (PySide6 6.12.0 — включая WebEngine, pyautogui 0.9.54, pynput 1.8.2, ruff 0.17.2, pytest 9.1.1).
- **Ближайшая веха:** приёмка **M2**, затем **M3 — модель сценариев (IR)**.

## Следующие шаги (по порядку)

1. **Ручная приёмка M2** (чек-лист в `plans/M2-gui-simple-mode.md`):
   запуск `python -m app`, пикер F8, клики по кнопке и F5, стоп F6 из любого окна,
   повторы N/∞, fail-safe, трей, оба диалога закрытия, восстановление настроек.
2. Слияние `feat/m2-gui-simple-mode` в `master` + запись в журнал.
3. **Спайк:** фоновые клики `PostMessage` в выбранное окно (курсор свободен) —
   прототип и матрица совместимости приложений; решение о включении в продукт.
4. Далее — по `ROADMAP.md` (M3: IR-сценарии, M4: Blockly, M5: упаковка).

### Материалы для GitHub-репозитория (About)

- **Описание (EN, основное):** `🧰 Windows auto-clicker with visual block scripting — snap blocks together to build click scenarios, no coding required. Python + PySide6 + Blockly.`
- **Описание (RU, альтернатива):** `Автокликер для Windows с визуальным программированием: сценарии кликов собираются из блоков, как конструктор — без кода.`
- **Topics:** `autoclicker, auto-clicker, automation, blockly, visual-programming, no-code, python, pyside6, qt, windows, mouse, macro, clicker`

---

## Известные проблемы / вопросы

- [ ] Выбрать конкретные версии PySide6 и QtWebEngine (тяжёлая зависимость,
      нужен план Б на случай проблем со сборкой PyInstaller).
- [ ] Решить, нужен ли `mouse` как третий бэкенд ввода (pyautogui иногда
      конфликтует с полноэкранными играми — возможно, понадобится raw input).
- [x] UX при срабатывании fail-safe: в консоли демо печатается traceback
      `pyautogui.FailSafeException`; в M2 заменить на понятное сообщение
      в статус-баре (это не баг, а сработавшая защита).
      (✅ 2026-10-25: `FailsafeTriggered` → `StopReason.FAILSAFE` →
      «Сработала защита: курсор в углу экрана — клики остановлены».)
- [ ] **Спайк после M2:** клики без захвата курсора (`PostMessage`
      `WM_LBUTTONDOWN/UP` в выбранное окно). Проверить совместимость
      (блокнот, браузер, игры на DirectInput/RawInput) и решить, включать ли
      как «фоновый режим». Ограничение платформы зафиксировано в
      `AI_CONTEXT.md` §3.1 (ADR №12): второй независимый курсор невозможен.
- [ ] Консольные логи с русским текстом в `cmd` могут отображаться в кракозябрах
      (кодировка консоли Windows). Лечится настройкой UTF-8-потока в логировании — M5.
- [x] Ручная приёмка M1: реальные клики и F5/F6/fail-safe на машине пользователя
      (✅ 2026-10-24: 100/100 кликов, все хоткеи работают; автотесты хоткеи
      не проверяют: `pynput.GlobalHotKeys` с версии 1.8.2 игнорирует
      injected-события, поэтому синтетические нажатия из тестов не срабатывают).
- [ ] Античит-риски: документировать, что проект предназначен для
      некоммерческого/офлайн-использования. (✅ частично: дисклеймер добавлен в README)
- [x] Выбрать лицензию и добавить файл `LICENSE` до публикации на GitHub.
      (✅ 2026-10-23: **MIT**, правообладатель Danil Momot, файл `LICENSE` создан,
      ADR №6 в `AI_CONTEXT.md`; осталось при сборке PyInstaller добавить NOTICE
      о LGPL-компонентах Qt рядом с `.exe`.)
- [x] Переименовать локальную папку `AutoClicker` → `ClicKit` и создать remote `ClicKit`.
      (✅ 2026-10-23: папка уже `ClicKit`, remote `origin` → `github.com/AkaDaka1/ClicKit`.)
