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
| 2026-10-24 | **M1 реализован** в ветке `feat/m1-core-engine` (5 коммитов): `core/input/backend.py` (ABC `InputBackend`, `Button`, фабрика `create_backend`), `core/input/pyautogui_backend.py` (`PyAutoguiBackend`, FAILSAFE=True, PAUSE=0), `core/executor.py` (`Executor` в `threading.Thread` + `threading.Event`, прерываемый интервал, `on_step`), `core/hotkeys.py` (`HotkeyManager` на `pynput.GlobalHotKeys`), `tests/test_executor.py` (5 тестов с `MockBackend`), `scripts/demo_click.py`; `ruff check`/`format` — чисто, `pytest` — 5 passed; ручная приёмка демо (клики, F5/F6, fail-safe) — за пользователем | 🚧 Ветка запушена в origin, приёмка вручную |

---

## Текущий статус

- **Этап:** **M1 — код готов** (ветка `feat/m1-core-engine`) — движок кликов, хоткеи и демо из консоли; ожидается ручная приёмка демо пользователем, затем слияние в `master`.
- **M0:** завершён — скелет проекта с рабочей точкой входа `python -m app`.
- **Название продукта:** **ClicKit** — «click it» + «kit» (конструктор); решение зафиксировано в `AI_CONTEXT.md` §3.3 (ADR №5).
- **Организационное:** папка переименована в `ClicKit`, GitHub-remote `origin` → `github.com/AkaDaka1/ClicKit` подключён.
- **Зависимости:** установлены (PySide6 6.12.0 — включая WebEngine, pyautogui 0.9.54, pynput 1.8.2, ruff 0.17.2, pytest 9.1.1).
- **Ближайшая веха:** **M2 — главное окно + «Простой режим»** (после приёмки M1).

## Следующие шаги (по порядку)

1. **Приёмка M1 (вручную):** запустить `python scripts/demo_click.py --x <X> --y <Y> --count 100 --interval 0.1`,
   проверить F5 / F6 / Esc и fail-safe (курсор в угол экрана); после этого —
   слияние `feat/m1-core-engine` в `master` и push.
2. **M2:** Главное окно с двумя режимами; «Простой режим»: координаты (пикер),
   интервал, кнопка мыши, число повторов, старт/стоп по хоткею и кнопкой; трей-иконка.
3. Далее — по `ROADMAP.md` (M3: IR-сценарии, M4: Blockly, M5: упаковка).

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
- [ ] Ручная приёмка M1: реальные клики и F5/F6/fail-safe на машине пользователя
      (автотесты хоткеи не проверяют: `pynput.GlobalHotKeys` с версии 1.8.2
      игнорирует injected-события, поэтому синтетические нажатия из тестов
      не срабатывают — это ожидаемо и защищает от ложных срабатываний).
- [ ] Античит-риски: документировать, что проект предназначен для
      некоммерческого/офлайн-использования. (✅ частично: дисклеймер добавлен в README)
- [x] Выбрать лицензию и добавить файл `LICENSE` до публикации на GitHub.
      (✅ 2026-10-23: **MIT**, правообладатель Danil Momot, файл `LICENSE` создан,
      ADR №6 в `AI_CONTEXT.md`; осталось при сборке PyInstaller добавить NOTICE
      о LGPL-компонентах Qt рядом с `.exe`.)
- [x] Переименовать локальную папку `AutoClicker` → `ClicKit` и создать remote `ClicKit`.
      (✅ 2026-10-23: папка уже `ClicKit`, remote `origin` → `github.com/AkaDaka1/ClicKit`.)
