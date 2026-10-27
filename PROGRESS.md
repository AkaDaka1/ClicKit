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
| 2026-10-25 | **M2 реализован** в ветке `feat/m2-gui-simple-mode` (11 коммитов): `core/settings.py` (JSON в `%APPDATA%`, атомарная запись), `position()` и `FailsafeTriggered` в `InputBackend`, `StopReason`/`on_finish` в `Executor`, `gui/executor_adapter.py`, `gui/hotkey_bridge.py`, `gui/picker.py`, `gui/simple_mode/{config,view}.py`, `gui/main_window.py` (две вкладки, трей, диалоги закрытия), `gui/tray.py`, `gui/icons.py`, `app/paths.py`, тёмная тема `resources/styles/dark.qss`, иконка `resources/icons/app.svg`; при первом запуске точка клика — центр экрана, точка `(0, 0)` блокируется (аварийный угол pyautogui); `ruff check`/`format` — чисто, `pytest` — 39 passed | ✅ Готово |
| 2026-10-25 | **Ручная приёмка M2 пройдена** (по чек-листу плана): главное окно в тёмной теме, пикер координат по F8, старт/стоп кнопкой и F5/F6, повторы и «Бесконечно», fail-safe, трей, оба диалога закрытия с «Запомнить выбор», восстановление настроек; ветка `feat/m2-gui-simple-mode` влита в `master` и запушена в `origin` | ✅ Готово |
| 2026-10-26 | Согласован план M3 (`plans/M3-ir-scenarios.md`): только `core` + консольное демо, узел `if` зарезервирован, циклы `repeat N`/`repeat ∞`, recorder отложен, формат `.acl.json` v1 | ✅ Готово |
| 2026-10-26 | **M3 реализован** в ветке `feat/m3-ir-scenarios` (8 коммитов): `core/worker.py` (`ThreadedWorker` + `StopReason`, `Executor` переведён на него), `core/ir/{nodes,schema,interpreter,storage}.py` (12 типов узлов, валидация с путями, лимиты, `.acl.json`), `core/scenario_runner.py`, `scripts/run_scenario.py` (+`--dry-run`), пример `resources/examples/click_pause_loop.acl.json`; 78 новых тестов (всего 117) | ✅ Готово |
| 2026-10-26 | **Ручная приёмка M3 пройдена:** пример `click_pause_loop.acl.json` отработал 22 действия («Сценарий выполнен»), F6/Esc работают; ветка `feat/m3-ir-scenarios` влита в `master` и запушена в `origin` | ✅ Готово |
| 2026-10-27 | Согласован план M4 (`plans/M4-blockly-editor.md`): Blockly 13.4.0 vendored, гибридный `.acl.json` (IR + `editor.workspace`), контекстные F5/F6, HTML-тулбар; `if`/`while` и recorder — вне M4 | ✅ Готово |
| 2026-10-27 | **M4 реализован** в ветке `feat/m4-blockly-editor` (9 коммитов): `scripts/vendor_blockly.py` + `resources/blockly/`, `bridge/{blockly_ir,scenario_file,web_channel}.py`, `gui/editor/{scenario_adapter,editor_view}.py`, страница Blockly (10 блоков, тёмная тема, тулбар, подсветка), контекстные F5/F6 и взаимное исключение; 180 автотестов, `ruff` чист | ✅ Реализовано, ожидает ручной приёмки |

---

## Текущий статус

- **Этап:** **M4 реализован** в ветке `feat/m4-blockly-editor` и ожидает
  ручной приёмки; после неё — merge в `master`.
- **M0:** завершён — скелет проекта с рабочей точкой входа `python -m app`.
- **M1:** завершён и влит в `master` — движок кликов, глобальные хоткеи, консольное демо.
- **M2:** завершён и влит в `master` — главное окно с двумя режимами, «Простой режим»
  (точка + пикер F8, кнопка мыши, интервал в мс, повторы/∞, старт-стоп кнопкой и F5/F6),
  тёмная тема, трей, настройки в `%APPDATA%\ClicKit\settings.json`, диалоги закрытия
  с «Запомнить выбор».
- **M3:** завершён — IR-формат `.acl.json` v1 (узлы `click`/`double_click`/`move`/
  `drag`/`delay`/`key`/`scroll`/`loop`/`sequence`, `if` зарезервирован), валидация
  с путями и лимитами, интерпретатор с мгновенным стопом, `ScenarioRunner` в потоке,
  атомарное сохранение/загрузка, консольный запуск `scripts/run_scenario.py`
  с `--dry-run`; 117 автотестов.
- **M4:** реализован — Blockly 13.4.0 вендорен локально (`resources/blockly/`),
  10 кастомных блоков на русском, редактор в `QWebEngineView` с тёмной темой
  и HTML-тулбаром, транслятор Blockly-JSON ↔ IR, гибридный `.acl.json`
  (IR + `editor.workspace`), подсветка текущего блока и ошибок, контекстные
  F5/F6 и взаимное исключение кликов/сценария; 180 автотестов.
- **Название продукта:** **ClicKit** — «click it» + «kit» (конструктор); решение зафиксировано в `AI_CONTEXT.md` §3.3 (ADR №5).
- **Организационное:** папка переименована в `ClicKit`, GitHub-remote `origin` → `github.com/AkaDaka1/ClicKit` подключён.
- **Зависимости:** установлены (PySide6 6.12.0 — включая WebEngine, pyautogui 0.9.54, pynput 1.8.2, ruff 0.17.2, pytest 9.1.1).
- **Ближайшая веха:** **M5 — полировка и упаковка** (после ручной приёмки M4).

## Следующие шаги (по порядку)

1. **Ручная приёмка M4** по чек-листу `plans/M4-blockly-editor.md`
   (сборка сценария drag-and-drop, `F5`/`F6`, подсветка, сохранение/открытие,
   подсветка ошибок); затем merge ветки `feat/m4-blockly-editor` в `master`.
2. **M5 — полировка и упаковка:** светлая тема, настройки хоткеев/языка,
   логи и дружелюбные ошибки, PyInstaller (включая `resources/blockly/` в `datas`).
3. **Спайк (опционально):** фоновые клики `PostMessage` в выбранное окно — прототип
   и матрица совместимости приложений.
4. **После M4:** условия `if`/`while` с чтением экрана, `recorder.py`,
   пикер координат прямо в поле блока, библиотека шаблонов.

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
- [ ] **Условия в сценариях (`if`, `loop while`) — M5+:** в схеме IR v1 тип `if`
      зарезервирован, интерпретатор выдаёт понятную ошибку; редактор M4
      намеренно не показывает эти блоки. Для реальных условий понадобится
      чтение экрана (`pixel()`) — отдельное решение.
- [ ] **`recorder.py` (запись действий мыши в IR) отложен** — логично после M4
      (M5): нужен режим записи и защита от самозаписи кликов.
- [ ] **PyInstaller + QtWebEngine (M5):** включить `resources/blockly/` целиком
      (JS, `msg/`, `media/`) в `datas`, добавить NOTICE об Apache-2.0/LGPL
      и проверить `.exe` на чистой Windows.
- [ ] **Web-тесты и QtWebEngine:** offscreen-тесты требуют
      `QTWEBENGINE_DISABLE_SANDBOX=1` и `QTWEBENGINE_CHROMIUM_FLAGS=--disable-gpu`;
      при недоступном Chromium смоук отключается `CLICKIT_SKIP_WEB=1`.
      Реальный рендер Blockly проверяется вручную на приёмке.
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
