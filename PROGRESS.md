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
| 2026-10-23 | Создана директория `plans/` для рабочих планов (тогда gitignored; с 2026-11-01 — публичная часть репозитория); план M0 зафиксирован в `plans/M0-skeleton.md`; `.gitignore` дополнен, шапка исправлена AutoClicker → ClicKit | ✅ Готово |
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
| 2026-10-27 | **M4 реализован** в ветке `feat/m4-blockly-editor` (10 коммитов): `scripts/vendor_blockly.py` + `resources/blockly/`, `bridge/{blockly_ir,scenario_file,web_channel}.py`, `gui/editor/{scenario_adapter,editor_view}.py`, страница Blockly (10 блоков, тёмная тема, тулбар, подсветка), контекстные F5/F6 и взаимное исключение; 180 автотестов, `ruff` чист | ✅ Готово |
| 2026-10-27 | **Ручная приёмка M4 пройдена** (по чек-листу `plans/M4-blockly-editor.md`): сборка сценария drag-and-drop, запуск кнопкой и `F5`/`F6` с подсветкой, сохранение/открытие `.acl.json`, подсветка ошибок, контекстные хоткеи; ветка `feat/m4-blockly-editor` влита в `master` и запушена в `origin` | ✅ Готово |
| 2026-10-28 | Согласован план M5 (`plans/M5-polish-packaging.md`): тема «системная/тёмная/светлая», язык только русский, редактируемые хоткеи, журналы, PyInstaller onefile, версия 1.0.0 | ✅ Готово |
| 2026-10-28 | **M5 реализован** в ветке `feat/m5-polish-packaging` (5 коммитов): `gui/theme.py` + `light.qss` + светлая тема Blockly, диалог настроек с `HotkeyEdit` и перезагрузкой слушателя, `app/logging_setup.py` (журнал, UTF-8, excepthook), `packaging/` (spec, ICO, NOTICE, version_info), `scripts/{make_icon,build_exe}.py`, нормализация хоткеев при загрузке настроек; 256 автотестов, `ruff` чист; локальная сборка `dist/ClicKit.exe` (220 МБ) запущена — окно создаётся, журнал пишется | ✅ Готово, ждёт приёмки |
| 2026-10-29 | Уточнён формат релиза по результатам замеров: onefile стартует ~58 с (распаковка QtWebEngine), onedir — ~2 с. Решено публиковать оба: `dist/ClicKit-win64.zip` (227.8 МБ, рекомендуется) и `dist/ClicKit.exe` (220.3 МБ); `build_exe.py` получил `--zip`/`--onefile`/`--both`, spec — режим `CLICKIT_ONEFILE`; zip проверен, версия свойств `.exe` — 1.0.0 | ✅ Готово |
| 2026-10-29 | **M5 влит в `master`** через PR #1 (merge `522da54`); merge проверен: деревья `origin/master` и ветки совпадают, конфликтов нет; локальная `master` обновлена, `ruff` и 256 тестов на `master` зелёные. Подготовлены релизные материалы: `CHANGELOG.md`, контрольные суммы артефактов | ✅ Готово |
| 2026-10-29 | **CI/CD на GitHub Actions:** `.github/workflows/ci.yml` (ruff + тесты на Python 3.11/3.12/3.13 + сборка `--zip` и смоук на `master`; `concurrency`, кэш pip, JUnit при падении) и `.github/workflows/release.yml` (тег `v*` или ручной запуск → полный CI → сверка тега с `APP_VERSION` → сборка → GitHub Release с `ClicKit-win64.zip` + `NOTICE.txt` + `SHA256SUMS.txt`, заметки из `CHANGELOG.md`, Pre-release для суффиксов, повторный запуск обновляет релиз). Добавлены `scripts/verify_release.py` (версия, артефакты, SHA-256, смоук-запуск offscreen) и `scripts/release_notes.py` (раздел CHANGELOG + флаг pre-release); `pyproject.toml`: `version` → `1.0.0`, `pythonpath`/`testpaths` для pytest; тесты `tests/test_release_tools.py` (16). Итог: `ruff` чист, 272 теста зелёные | ✅ Готово |
| 2026-10-31 | Создан план M6 «DevOps: Docker + тестовые релизы» — `plans/M6-docker.md`: цель, критерий готовности, согласованные параметры (полный стек: Linux-тесты в контейнере, Windows-образ сборки, GHCR, CI-интеграция, dev-релизы; Windows-матрица CI не трогается; долгоживущей `dev`-ветки нет — только механизм), модули, ADR-черновики, 7 коммитов, чек-лист приёмки, **граф задач T0.1–T6.1** с зависимостями и параллельными волнами; новая практика зафиксирована в `AGENTS.md` («Планы вех»): задачи вех выполняются по отдельности в разных сессиях по ID; ADR №33–35 внесены в `AI_CONTEXT.md` §3.3 | ✅ Готово |
| 2026-10-31 | **T0.1 (M6) выполнена — Docker проверен:** Docker Desktop 4.97.0 (244584), engine 29.9.2, compose v5.6.1, backend WSL2; `docker run hello-world` и `python:3.11-slim` (3.11.18) — ок. Windows-часть: Docker Desktop был установлен без компонента Windows-контейнеров (`noWindowsContainers: true`) — компонент доустановлен инсталлятором + перезагрузка машины, после чего `-SwitchWindowsEngine` дал контекст `desktop-windows`; `mcr.microsoft.com/windows/servercore:ltsc2022` (5.05 GB, isolation=hyperv) → `cmd /c echo ok` = `ok`; движок возвращён на Linux. Попутно: pull'ы Docker Hub периодически падают с `EOF` через прокси Docker Desktop — помогает ретрай | ✅ Готово |
| 2026-10-31 | **T1.1 (M6) выполнена — Docker-среда тестов собрана:** `docker/Dockerfile.test` (python:3.11-slim + apt-пакеты Qt/WebEngine/Xvfb, pip из `requirements.txt`, ENTRYPOINT `python -m pytest`), `.dockerignore`, `docker-compose.yml` (сервис `test`, offscreen-переменные Qt, `init: true`). Образ `clikit-test:local` — 421 MB; `docker compose run test` стартует и собирает тесты. Первая сборка падала на `evdev` (pynput на Linux): добавлены временные `gcc`+`libc6-dev`+`linux-libc-dev` — ставятся и удаляются в том же слое. Ожидаемые 12 ошибок сбора (`libEGL.so.1`, `DISPLAY`) — вход в гейт T1.2; закоммичено (`3877f33`, `feat: docker-среда для автотестов`) — по решению пользователя до T1.2. Попутно: Docker Desktop был на Windows-контейнерах — `docker context use desktop-linux` вернул Linux-движок; pull `python:3.11-slim` повторили после `EOF` | ✅ Готово |
| 2026-10-31 | **T3.1 (M6) выполнена — Windows-образ сборки:** `docker/Dockerfile.build-win` (servercore:ltsc2022 + Python 3.11.9 из NuGet flat-container, зависимости отдельным слоем, явный `COPY` исходников, ENTRYPOINT `python scripts/build_exe.py`) и `.dockerignore`. Образ `clikit-build-win:local` — 5.94 ГБ, сборка ~25 мин (pip через прокси контейнера). `docker run --rm -v "<копия репозитория>:C:/work" clikit-build-win:local --zip` → `ClicKit-win64.zip` 230.6 МБ (3286 записей, Blockly в `_internal/resources/`) + `SHA256SUMS.txt`; артефакт прошёл на хосте `python scripts/verify_release.py --dist … --smoke`. Особенности Windows-контейнеров (в §9 плана): legacy-билдер без BuildKit (`.dockerignore` обязателен), `WORKDIR C:\work` → «invalid absolute path» (пишем `C:/work`, монтируем `-v "<путь>:C:/work"`), `www.nuget.org` не резолвится в контейнере (качаем с `api.nuget.org`), VC++ redist не нужен (PySide6 несёт `msvcp140`/`vcruntime140`). Движок возвращён на Linux | ✅ Готово |
| 2026-11-01 | **T1.2 (M6) — зелёные тесты в контейнере:** `docker/Dockerfile.test` — полный apt-список (xvfb+xauth, libtk8.6, libegl1/gles2, drm/gbm, pango/atk/at-spi, libxcb-*), ENTRYPOINT `xvfb-run --auto-servernum python -m pytest` (pynput/pyautogui требуют `DISPLAY`). 274 passed за ~8 с, но exit 134 — «Fatal Python error: bool_dealloc» при финализации (PySide6 + QtWebEngine, живые потоки Chromium); закрытие окон + `gc` недостаточно. Решение: `tests/conftest.py` — хуки `pytest_sessionfinish` (Linux + загружен `PySide6.QtWebEngineCore`: closeAllWindows + gc) и `pytest_unconfigure` (`os._exit(exitstatus)`, JUnit и сводка уже записаны). Финальная проверка: 274 passed, exit 0, `junit.xml` — `tests="274" failures="0"`; на хосте (Windows) `pytest -q` и `ruff` тоже зелёно. Commit `5ed9d93` | ✅ Готово |
| 2026-11-01 | **T2.1 (M6) — job `tests-docker` в `ci.yml`:** прежний job был нерабочим (`docker build` без `-t` — образ без тега, а `docker run clikit-test:local` на чистом раннере его не найдёт; ENTRYPOINT конфликтовал с `python -m pytest`). Исправлено: сборка `-t clikit-test:ci` из контекста PR, `--init`, env Qt/WebEngine, bind mount `reports/`, `--junitxml`, артефакт `junit-docker` при падении. Локально та же команда — 274 passed, exit 0. Чекпоинт: **PR #2 — все job зелёные** (lint, tests 3.11–3.13, tests-docker 68 c; run 41317645348). Commit `e5225d4` | ✅ Готово |
| 2026-11-01 | Созданы планы **M7–M11** (`plans/M7-cloud-service.md`, `M8-observability.md`, `M9-infrastructure.md`, `M10-delivery.md`, `M11-security-resilience.md`) и индекс `plans/README.md`: цель и критерий готовности, параметры, модули, ADR №36–50, граф задач T0.1–T5.1, волны, риски, журналы. M6 не переделывается: T3.2/T4.1/T5.1/T6.1 остаются в M6, новые вехи их не дублируют | ✅ Готово |
| 2026-11-01 | `plans/` исключён из `.gitignore` — планы вех теперь публичная часть репозитория; обновлены `AI_CONTEXT.md` (§3.2, §3.3, §4, §5, журнал), `ROADMAP.md` (M6–M11), `AGENTS.md` (публичные планы), `PROGRESS.md`, шапка `plans/M6-docker.md`; добавлен индекс `plans/README.md` | ✅ Готово |
| 2026-11-01 | **M6 закрыт по чекпоинтам (T3.2, T4.1, T5.1, T6.1):** `docker.yml` публикует в GHCR `clikit-test` и `clikit-build-win` (run 41336011415 — Linux 1m43s, Windows 9m39s); `release.yml` собирает релиз в Windows-контейнере (dry-run 41337101336 — сборка 8m21s, smoke и артефакты зелёные, publish пропущен); `dev-release.yml` создаёт и обновляет draft-релиз `dev` (runs 41337281967 → 41338058699, один релиз, ассеты обновлены через `--clobber`). Найдено и исправлено: Windows runner без Buildx (legacy `docker build`/`docker push`), старый тег `v1.0.0` без `docker/` (dry-run собирает `master`), `HTTP 403` при публикации (`contents: write` на job). Локально: `ruff check`, `ruff format --check` — чисто; CI на `9a72d08` — зелёный | ✅ Готово |
| 2026-11-02 | **T0.1 (M7) — контракт ClicKit Cloud:** создан `docs/api.md` — общие соглашения (UTC, UUIDv4, `/v1`, OpenAPI), авторизация (`X-API-Key`, отдельный admin-ключ на удаление, fail-closed без ключа), общие заголовки (`X-Request-ID`, `Idempotency-Key`, `ETag`/`If-None-Match`), ошибки RFC 7807 с URN-типами (401/403/404/409/413/415/422/500/503), 9 эндпоинтов с телами и ответами, валидация IR только через `core.ir.schema` (нормализованный IR в БД, `editor.workspace` не публикуется), лимиты (1 МБ тело, 10 000 узлов, глубина 32, 50 ошибок), идемпотентность 24 ч с хэшем тела и гонкой через unique-индекс, схема PostgreSQL 16, env-конфигурация, контракт `cloud/client.py` (retry только 5xx/таймауты, jitter) и CLI с кодами выхода. План M7 §5.3/5.4 уточнён, T0.1 отмечена ✅, журнал задачи заполнен. Код не писался (по чекпоинту задачи) | ✅ Готово |
| 2026-11-02 | **T1.1 (M7) — скелет ClicKit Cloud:** `service/app/{main,config,version,schemas}.py` и `api/v1/health.py`; `requirements-service.txt` (FastAPI/uvicorn/SQLAlchemy/Alembic/psycopg/httpx + тесты). Настройки — только env, читаются в `lifespan` (импорт без секретов), проверка при старте: без `CLICKIT_API_KEY` процесс завершается `ServiceConfigError` (fail-closed). Эндпоинты: `/healthz` (200 без БД), `/version` (версия, git sha из env, `ir_format_version` из `core.ir.nodes`), `/metrics` (заготовка Prometheus `clikit_build_info`, экранирование меток). Проверено вживую: `uvicorn service.app.main:app --port 8010` → 200/200/200 и `/openapi.json` 200; запуск без ключа — `Application startup failed`. Тесты `tests/service/` (15: конфиг + API), всего **289 passed**; `ruff` чисто | ✅ Готово |
| 2026-11-02 | **T1.2 (M7) — БД, модели, Alembic, `/readyz`:** `service/app/db.py` (`Database`: engine с таймаутом 5 с, `session`/`session_scope`, `check()` = `SELECT 1`, `dispose`), `service/app/models.py` (`scenarios` и `crash_reports` по `docs/api.md` §8: CHECK, `char(64)`, `jsonb`, `timestamptz`, индексы и unique по `idempotency_key`), Alembic (`service/alembic.ini`, `service/migrations/{env.py,script.py.mako,versions/0001_initial_schema.py}`, URL только из `CLICKIT_DB_URL`). `CLICKIT_DB_URL` стал обязательным (fail-closed); engine создаётся в `lifespan` и закрывается на остановке, `/readyz` — 200/503 без деталей ошибки, `/healthz` жив без БД. Проверено вживую на `postgres:16` (Docker, порт 55432): `alembic upgrade head` → `alembic_version=0001`, схема совпала с §8, `alembic check` без расхождений, `downgrade base`/`upgrade head` повторяются; `uvicorn` → `/readyz` 200, после `docker stop` — 503 при `/healthz` 200, после `docker start` — снова 200. Тесты: 35 в `tests/service/` (всего **309 passed**), `ruff check`/`format --check` чисто | ✅ Готово |
| 2026-11-03 | **T2.1 (M7) выполнена — CRUD сценариев:** `service/app/{scenario_service,repository,errors,middleware}.py`, `api/v1/scenarios.py`, `api/deps.py`; `POST /v1/scenarios` (201 с `Idempotency-Key` 24 ч, replay с `Idempotent-Replay: true`, 409 при другом теле, 413/415/422), `GET /v1/scenarios/{id}` (200 с `ETag` и `If-None-Match` 304, weak comparison), `GET /v1/scenarios` (пагинация `limit`/`offset`, `created_at DESC`), `DELETE /v1/scenarios/{id}` (204/404); `BodySizeLimitMiddleware` (общий слой лимита `CLICKIT_MAX_BODY_BYTES` до разбора, действует и на crash-отчёты); `ScenarioRepository` с обработкой `IntegrityError` (гонка двух запросов → replay или 409); валидация IR через `core.ir.schema.scenario_from_mapping` (ADR №37), нормализация `Scenario.to_mapping()`, хэш `sha256` канонический. Проверено вживую: `uvicorn` + PostgreSQL 16 (Alembic `0001`), все эндпоинты, ETag strong/weak, replay, конфликт, лимиты 1 МБ, problem+json с путями. Тесты: 113 service (`tests/service/test_{scenarios_api,idempotency,scenario_service}.py`, SQLite + PostgreSQL 16), всего **387 passed**; `ruff check`/`format --check` чисто. Commit `83f9585` | ✅ Готово |
| 2026-11-04 | **T2.2 (M7) выполнена — приём crash-отчётов:** `service/app/crash_service.py` (валидация `app_version` 1–64 / `os` ≤64 / `error_hash` ровно 64 hex с нормализацией в lowercase; санитайзер PII: домашние каталоги `C:\Users\*`, `/home/*`, `/Users/*` → `<пользователь>`; обрезка traceback до 16 384 символов), `service/app/api/v1/crash_reports.py` (`POST /v1/crash-reports` — 202 `{id, received_at}`, публичный эндпоинт без `X-API-Key`; ошибки 415/422 в problem+json со списком `errors`; тело отчёта не логируется), схема `CrashReceipt` в `schemas.py`, роутер зарегистрирован в `main.py`; лимит тела 1 МБ наследуется от общего `BodySizeLimitMiddleware` (T2.1). Ретеншн 30 дней документирован в `docs/api.md` §5.9 (фоновый очиститель — M8/M11). Тесты: 23 новых (`tests/service/test_crash_reports_api.py`: приём, санитайзер для Windows/Unix/macOS, обрезка, валидация, 415/413/422, OpenAPI), всего 136 service и **410 passed** полным прогоном; `ruff check`/`format --check` чисто. Commit `000be31` | ✅ Готово |
| 2026-11-04 | Уборка после параллельных сессий T2.1/T2.2: удалены worktree `ClicKit-t22`, локальная ветка `feat/m7-t22-crash-reports` (`9dcef38`, альтернативная реализация T2.2, не влита) и stash с устаревшим T2.1; почищены кэши `__pycache__`/`.pytest_cache`/`.ruff_cache`; исправлена ссылка на тесты в `crash_service.py` (`test_crash_reports_api.py`). master = `origin/master`, 136 service-тестов и `ruff` зелёные | ✅ Готово |
| 2026-11-04 | **T3.1 (M7) выполнена — API-ключи и корреляция запросов:** `service/app/security.py` (роли `write`/`admin`, `hmac.compare_digest`, 401 без/с неверным ключом, 403 при недостаточной роли; роли не иерархичны: admin-ключ не публикует, write-ключ не удаляет при заданном `CLICKIT_ADMIN_API_KEY`), `service/app/request_id.py` (`RequestContextMiddleware`: валидный входящий `X-Request-ID` (32–64, `[A-Za-z0-9._-]`) пробрасывается, иначе UUID4; заголовок на всех ответах, включая 413; `ContextVar` + `RequestIdFilter` для журнала), единые обработчики `RequestValidationError`/`HTTPException`/`Exception` в `errors.py` (URN 400/405; 500 без деталей, traceback только в журнале с `request_id`), deps `require_write_key`/`require_delete_key` и схема `ApiKey` в OpenAPI; `BodySizeLimitMiddleware` берёт id из scope. Проверено: 401/403/201/204, эхо валидного и замена невалидного id, 404/405/422/413/500 в problem+json, ключ отсутствует в ответах и журнале. Тесты: 26 новых (`test_auth.py`, `test_request_id.py`), service — 162, всего **436 passed**; `ruff check`/`format --check` чисто. Commit `105c9dc` | ✅ Готово |
| 2026-11-04 | **T3.2 (M7) выполнена — Docker-образ сервиса:** `docker/Dockerfile.service` (multi-stage `builder` → `runtime`: venv с зависимостями, non-root `UID/GID 10001`, `HEALTHCHECK` раз в 10 с через `python -m service.app.healthcheck` только по `/healthz`, exec-форма uvicorn и `--timeout-graceful-shutdown 20`); `service/app/healthcheck.py` (короткая ошибка без traceback, URL из env); `requirements-service.txt` разделён на runtime и `requirements-service-test.txt` (pytest/coverage в образ не попадают), `.dockerignore` дополнен `.env*`/отчётами покрытия. Проверено вживую: образ `clikit-service:local` 332 МБ, контейнер healthy, `uid=10001`, `/healthz`/`/readyz`/`/version` 200, `POST`/`GET` сценария на PostgreSQL 16 (Alembic `0001`), `docker stop` → exit 0 и graceful shutdown. Тесты: 8 новых (`test_dockerfile.py`, `test_healthcheck.py`), всего **444 passed**; `ruff check`/`format --check` чисто. Commit `05a6624` | ✅ Готово |
| 2026-11-05 | **T4.1 (M7) выполнена — локальный compose Cloud:** `docker-compose.cloud.yml` — PostgreSQL 16 с томом `pgdata` и healthcheck `pg_isready`, одноразовый `migrate` (`python -m alembic upgrade head`, `command: []` после замены ENTRYPOINT), API с `${CLICKIT_API_PORT:-8000}`, ожиданием здоровой БД и успешных миграций; секреты обязательны через `${VAR:?}` и `.env`. Добавлены `.env.example` (только заготовки), `!.env.example` в `.gitignore`, раздел «Локальный запуск» в `docs/api.md`, краткое упоминание в README и 7 статических тестов `tests/service/test_compose_cloud.py`. Проверено вживую: `up -d --build` → `migrate` exit 0 (`alembic_version=0001`), API healthy, `/healthz`/`/readyz`/`/version` 200, `POST`/`GET`/list сценария; остановка БД — `/readyz` 503 при `/healthz` 200, после старта снова 200; `down` → `up -d` — сценарий сохранился, `down -v` удаляет данные. Тесты: 450 passed, 1 нестабильный QtWebEngine-тест прошёл при повторном запуске (вне задачи); `ruff` чисто. Commit `0c2dee8` | ✅ Готово |
| 2026-11-05 | **Оформление репозитория:** новые скриншоты «Простой режим» и «Редактор сценариев» (`docs/img/`) через offscreen-скрипт `scripts/make_screenshots.py` (QT_QPA_PLATFORM=offscreen, ожидание `window.__ckReady` через `runJavaScript`, курсор не двигается — запускался существующий демо-сценарий); README дополнен бейджами (CI, Release, License, Python, Ruff, Windows, PySide6, Blockly, Cloud, GHCR, PRs welcome), блоками скриншотов, mermaid-диаграммами архитектуры и картой репозитория (EN и RU), статусы M7 обновлены на «в работе»; созданы `CONTRIBUTING.md`, `SECURITY.md` (приватное отчётление через GitHub Security Advisories, модель угроз и не-уязвимости), `CODE_OF_CONDUCT.md` (Contributor Covenant 2.1), формы issues `.github/ISSUE_TEMPLATE/{bug_report,feature_request,config}.yml`, `.github/PULL_REQUEST_TEMPLATE.md` и `.editorconfig`; `AI_CONTEXT.md` §3.2 дополнен. `ruff check`/`format --check` — чисто | ✅ Готово |
| 2026-11-12 | **T4.2 (M7) выполнена — клиент публикации сценариев:** `cloud/client.py` — `CloudClient` (таймаут 5 с на попытку, до 3 попыток, паузы `0.5, 1, 2` с ±25 % jitter только для 5xx/таймаутов/сетевых ошибок, 4xx без повтора) и иерархия ошибок по problem+json (`CloudError` → `CloudAuthError` 401/403, `CloudNotFoundError` 404, `CloudConflictError` 409, `CloudTooLargeError` 413, `CloudValidationError` 422 с `issues`, `CloudServerError` 5xx/сеть), dataclass `PublishedScenario`/`ScenarioPage`/`CrashReceipt`; `scripts/cloud_publish.py` — подкоманды `publish`/`download`/`list`/`delete`/`crash-report`, URL и ключ из `--url`/`--api-key` или env `CLICKIT_CLOUD_URL`/`CLICKIT_API_KEY`, коды выхода 0/2/3/4/5/6 по контракту `docs/api.md` §10, локальная валидация IR до отправки, атомарная запись скачанного файла. Проверено вживую на `docker compose -f docker-compose.cloud.yml`: публикация, список, скачивание (файл проходит `run_scenario.py --dry-run`), replay идемпотентности с тем же id, 409 при другом теле (код 5), неверный ключ → 3, неизвестный id → 4, остановленный API → 6 после двух попыток, crash-отчёт → 202 (в БД виден PII-санитайзер). 44 новых теста (`tests/service/test_cloud_client.py`, `tests/service/test_cloud_publish_cli.py`), service — 221, полный прогон **495 passed**; `ruff check`/`format --check` чисто | ✅ Готово |
| 2026-11-05 | **Пост-фиксы оформления:** выставлены GitHub-топики репозитория (python, sqlalchemy, postgresql, fastapi, alembic, pyside6, qt6, blockly, pyautogui, pynput, pyinstaller, windows, auto-clicker, automation, docker — через `gh api`); скриншоты переделаны без «квадратиков» вместо текста: `make_screenshots.py` теперь рендерит окно на нативной платформе с `WA_DontShowOnScreen` (окно не появляется, мышь не двигается, шрифты системные; у offscreen-платформы Qt на Windows нет шрифтовой базы; запасной режим — `CLICKIT_SHOTS_OFFSCREEN=1`); починен CI (`test_page_loads_and_has_starter_blocks` падал на раннере: внутренний таймаут `eval_js` 2 с меньше времени прогрева Chromium — `wait_js` теперь отдаёт опросу весь оставшийся бюджет и ловит `TimeoutError`, дефолт ожидания 30 с) | ✅ Готово |
| 2026-11-12 | **T5.1 (M7) выполнена — тесты сервиса и job `service-tests` в CI:** в `ci.yml` добавлен отдельный job `service-tests` на `ubuntu-latest` с сервисным контейнером `postgres:16` (`pg_isready`, `CLICKIT_TEST_DB_URL` → `localhost:5432/clikit_test`): `tests/service` проверяют уникальный индекс идемпотентности, `JSONB` и `timestamptz` на настоящей СУБД, локально без переменной — на файловой SQLite. Покрытие `service/` считается с ветвями, порог 80 % задан в `pyproject.toml` (`[tool.coverage.run]`/`[tool.coverage.report]`, недостижение роняет job), JUnit и `coverage.xml` сохраняются артефактом `service-reports`. Конфигурацию страхуют 5 статических тестов `tests/service/test_ci_workflow.py`; `AGENTS.md` дополнен локальной командой с покрытием. Проверено: 226 service-тестов на PostgreSQL 16 — 95.12 % (8.9 с в CI), полный прогон **500 passed**, `ruff check`/`format --check` чисто; PR #6 (run 43277921558) — все job зелёные, `service-tests` 43 с. ADR №58, схема CI в `AI_CONTEXT.md` §3.4 | ✅ Готово |
| 2026-11-12 | **T6.1 (M7) выполнена — документация ClicKit Cloud:** создан `docs/cloud.md` — зачем сервис, архитектура, требования, запуск с чистой машины (PowerShell и bash), проверка `/healthz`/`/readyz`/`/version`, публикация/список/скачивание через CLI, эндпоинты, коды ошибок и лимиты, миграции, тесты, эксплуатация (журналы, `pg_dump`/restore, ретеншн), диагностика и безопасность; `docs/api.md` дополнен перекрёстными ссылками и разделом «Связанные документы»; README (EN/RU) — M7 ✅, расширенный раздел Cloud с причиной и быстрым стартом; `.env.example` и `docker-compose.cloud.yml` ссылаются на руководство; `AI_CONTEXT.md` §3.3 — ADR №59; 7 статических тестов `tests/service/test_cloud_docs.py` (ссылки, переменные, эндпоинты, коды CLI). Проверено на чистом окружении: `compose down -v --rmi local` → `up -d --build`, контейнеры healthy, `migrate` exit 0, публикация/список/скачивание (файл проходит `run_scenario.py --dry-run`), replay по `Idempotency-Key`, удаление и 404, crash-отчёт с PII-санитайзером, `/readyz` 503 при остановленной БД и 200 после старта, данные и `pg_dump` переживают `down`/`up`; тесты: 7 новых (`tests/service/test_cloud_docs.py`), service — 233, покрытие 96.5 % (SQLite), полный прогон **507 passed**, `ruff check`/`format --check` чисто. PR #7 (run 43326940563) — все job зелёные, включая `service-tests` на PostgreSQL 16 | ✅ Готово |

---

## Текущий статус

- **Этап:** **M6 завершён** (Docker + тестовые релизы), удалённые чекпоинты
  подтверждены реальными прогонами GitHub Actions; **M7 завершён** (T0.1–T6.1:
  контракт API, скелет сервиса, БД и миграции, CRUD сценариев, приём
  crash-отчётов, API-ключи и корреляция запросов, production-образ сервиса,
  локальный compose API + PostgreSQL, клиент публикации, тесты сервиса в CI,
  документация), M8–M11 запланированы.
  Релиз **1.0.0** опубликован
  2026-10-29 (GitHub Release: `ClicKit-win64.zip`, NOTICE, SHA256SUMS).
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
- **M4:** завершён и влит в `master` — Blockly 13.4.0 вендорен локально
  (`resources/blockly/`), 10 кастомных блоков на русском, редактор в
  `QWebEngineView` с тёмной темой и HTML-тулбаром, транслятор Blockly-JSON ↔ IR,
  гибридный `.acl.json` (IR + `editor.workspace`), подсветка текущего блока
  и ошибок, контекстные F5/F6 и взаимное исключение кликов/сценария;
  180 автотестов.
- **M5:** завершён и влит в `master` (PR #1) — темы `system`/`dark`/`light`
  для GUI и Blockly с реакцией на тему Windows, диалог настроек с записью
  хоткеев (проверка конфликтов, применение без перезапуска), журнал в
  `%APPDATA%\ClicKit\logs\app.log` с ротацией и UTF-8, excepthook с понятным
  диалогом, PyInstaller (`packaging/ClicKit.spec`, `app.ico`, NOTICE,
  свойства версии 1.0.0): onedir-архив и onefile `.exe`; 256 автотестов.
- **Название продукта:** **ClicKit** — «click it» + «kit» (конструктор); решение зафиксировано в `AI_CONTEXT.md` §3.3 (ADR №5).
- **Организационное:** папка переименована в `ClicKit`, GitHub-remote `origin` → `github.com/AkaDaka1/ClicKit` подключён.
- **CI/CD:** GitHub Actions — `ci.yml` (ruff + тесты 3.11–3.13, сборка архива на `master`), `release.yml` (тег `v*` → CI → сборка → GitHub Release); ADR №30–32, схема в `AI_CONTEXT.md` §3.4.
- **M6 (Docker + тестовые релизы):** план выполнен 2026-10-31/2026-11-01 — `plans/M6-docker.md`
  с графом задач T0.1–T6.1 (волны: T0.1 → T1.1∥T3.1 → T1.2 → T2.1∥T3.2 →
  T4.1∥T5.1 → T6.1); ADR №33–35; задачи выполняются по отдельности в разных
  сессиях по ID (практика зафиксирована в `AGENTS.md`). Запущено задач: 6 —
  **T0.1 ✅** (Docker Desktop 4.97.0: `hello-world`, compose v5.6.1,
  Windows-движок → `servercore:ltsc2022` → `ok`, движок возвращён на Linux);
  **T1.1 ✅** (образ `clikit-test:local` собран: Dockerfile.test, `.dockerignore`,
  `docker-compose.yml`); **T3.1 ✅** (образ `clikit-build-win:local` собирает
  релизный zip в Windows-контейнере); **T1.2 ✅** (274 теста зелёны в контейнере:
  `xvfb-run` + apt-пакеты Qt/WebEngine, обход падения PySide6 на финализации);
  **T2.1 ✅** (job `tests-docker` в `ci.yml`; PR #2 — lint + tests 3.11–3.13 +
  tests-docker зелёные); **T3.2 ✅** (`docker.yml` → GHCR, run 41336011415),
  **T4.1 ✅** (контейнерная сборка `release.yml`, dry-run 41337101336),
  **T5.1 ✅** (`dev-release.yml`, runs 41337281967 → 41338058699) и **T6.1 ✅**
  (документация). Все чекпоинты подтверждены прогонами на GitHub.
- **M7–M11 (планы созданы 2026-11-01):** **M7** — ClicKit Cloud (FastAPI +
  PostgreSQL + Docker, `/v1/scenarios`); **M8** — метрики/логи/трейсы,
  Grafana/Loki/Tempo, алерты, SLO 99.5%; **M9** — Terraform + облако + k3s +
  Helm + HTTPS; **M10** — CD staging/prod, откат, DORA; **M11** — сканирование,
  SBOM, нагрузка, бэкапы, chaos. Планы публичны: `plans/README.md`.
- **M7 (ClicKit Cloud):** план `plans/M7-cloud-service.md`, задачи T0.1–T6.1.
  **T0.1 ✅** (2026-11-02): контракт API `docs/api.md` — авторизация
  write/admin-ключами и fail-closed, RFC 7807 с URN-типами, 9 эндпоинтов,
  лимиты, идемпотентность 24 ч, схема PostgreSQL 16, env-конфигурация,
  контракт клиента и CLI. **T1.1 ✅** (2026-11-02): скелет сервиса
  (`service/app/`), `/healthz`, `/version`, `/metrics`-заготовка, настройки
  из env с проверкой при старте; `uvicorn service.app.main:app` отвечает 200.
  **T1.2 ✅** (2026-11-02): `service/app/db.py` и `models.py`, Alembic
  (`service/alembic.ini`, `service/migrations/versions/0001_initial_schema.py`),
  обязательный `CLICKIT_DB_URL`, `/readyz` 200/503; миграции проверены на
  `postgres:16` в Docker. **T2.1 ✅** (2026-11-03): CRUD сценариев —
  `service/app/{scenario_service,repository,errors,middleware}.py`,
  `api/v1/scenarios.py`; `POST /v1/scenarios` (201 с `Idempotency-Key`, replay,
  409/413/415/422), `GET /v1/scenarios/{id}` (200 с `ETag`, 304 weak/strong),
  `GET /v1/scenarios` (пагинация), `DELETE` (204/404); `BodySizeLimitMiddleware`
  (общий слой лимита); валидация IR через `core.ir.schema` (ADR №37); 113
  service-тестов (SQLite + PostgreSQL 16), всего **387 passed**.
  **T2.2 ✅** (2026-11-04): приём crash-отчётов —
  `service/app/crash_service.py` и `api/v1/crash_reports.py`;
  `POST /v1/crash-reports` (202, публичный без ключа), санитайзер PII
  (домашние пути → `<пользователь>`), обрезка traceback до 16 КБ,
  валидация `app_version`/`os`/`error_hash`; ретеншн 30 дней описан
  в `docs/api.md` §5.9; 23 теста, всего **410 passed**.
  **T3.1 ✅** (2026-11-04): API-ключи и корреляция —
  `service/app/security.py` (write/admin-роли, `hmac.compare_digest`,
  401/403), `service/app/request_id.py` (`RequestContextMiddleware`,
  валидация и эхо `X-Request-ID` на всех ответах, `ContextVar` в журнале),
  единые problem+json-обработчики `RequestValidationError`/`HTTPException`/
  `Exception`; 26 тестов, всего **436 passed**.
  **T3.2 ✅** (2026-11-04): production-образ — `docker/Dockerfile.service`
  (multi-stage, non-root `10001`, `HEALTHCHECK` через
  `service/app/healthcheck.py`), разделение runtime/тестовых зависимостей;
  образ 332 МБ, healthy, graceful shutdown по SIGTERM; 8 тестов, всего
  **444 passed**.
  **T4.1 ✅** (2026-11-05): `docker-compose.cloud.yml` — PostgreSQL 16 с томом
  `pgdata`, одноразовый `migrate` (`alembic upgrade head`) и API, который
  ждёт здоровую БД и миграции; `.env.example`, секреты только из `.env`;
  проверено `up -d`/`down`, сохранность данных и 503 `/readyz` без БД;
  7 статических тестов.
  **T4.2 ✅** (2026-11-12): клиент `cloud/client.py` (retry только на
  5xx/таймаут/сеть, jitter, иерархия `CloudError`) и
  `scripts/cloud_publish.py` (`publish`/`download`/`list`/`delete`/
  `crash-report`, коды выхода 0/2/3/4/5/6); проверено вживую на compose;
  44 теста. **T5.1 ✅** (2026-11-12): job `service-tests` на `ubuntu-latest`
  с сервисным PostgreSQL 16 (`CLICKIT_TEST_DB_URL`), покрытие `service/`
  с ветвями и порогом 80 % в `pyproject.toml`, JUnit и `coverage.xml`
  артефактом; 226 тестов, 95.12 %; PR #6 — все job зелёные.
  **T6.1 ✅** (2026-11-12): документация — `docs/cloud.md` (запуск с чистой
  машины, CLI, эксплуатация, диагностика), перекрёстные ссылки в `docs/api.md`,
  README (EN/RU) с M7 ✅ и быстрым стартом, ADR №59; 7 статических тестов
  документации. **M7 закрыт по всем задачам.**
- **Зависимости:** установлены (PySide6 6.12.0 — включая WebEngine, pyautogui 0.9.54, pynput 1.8.2, ruff 0.17.2, pytest 9.1.1); для сборки — PyInstaller 6.22.3; для сервиса (M7) — fastapi 0.162.0, uvicorn 0.54.0, httpx 0.28.1, SQLAlchemy 2.1.6, Alembic 1.20.1, psycopg 3.3.6 (T1.2); тестовые зависимости сервиса вынесены в `requirements-service-test.txt` (T3.2).
- **Ближайшая веха:** **M8 — наблюдаемость** (`plans/M8-observability.md`):
  JSON-логи и полноценный `/metrics`, Prometheus/Grafana/Loki/Tempo, алерты,
  SLO 99.5 % и error budget, runbook. M7 завершён: контракт `docs/api.md`,
  скелет сервиса, БД и Alembic, CRUD сценариев, crash-отчёты, API-ключи и
  `X-Request-ID`, production-образ, локальный compose, клиент/CLI, тесты и CI,
  документация `docs/cloud.md`.

## Следующие шаги (по порядку)

1. **M6 выполнен** — все чекпоинты (T0.1–T6.1) подтверждены прогонами
   GitHub Actions; повторный запуск `Dev release` обновляет draft `dev`.
2. **Защита `master`** (Settings → Branches): обязательные проверки `lint`,
   `tests`, `tests-docker` и `service-tests`, запрет прямого push, обязательный PR,
   удаление ветки после merge; почистить влитые `feat/*`-ветки.
4. **M7 — ClicKit Cloud выполнен** (`plans/M7-cloud-service.md`): T0.1 контракт ✅ →
   T1.1 скелет ✅ → T1.2 БД ✅ → T2.1/T2.2 CRUD и crash-отчёты ✅ →
   T3.1 ключи и request_id ✅ → T3.2 Dockerfile ✅ → T4.1 compose ✅ →
   T4.2 клиент и CLI ✅ → T5.1 тесты/CI ✅ → T6.1 документация ✅. Запуск и
   эксплуатация — `docs/cloud.md`; для локальной проверки:
   `copy .env.example .env` (заполнить ключи), `docker compose -f
   docker-compose.cloud.yml up -d --build`; для БД без compose — `postgres:16`
   в Docker и `alembic -c service/alembic.ini upgrade head` при заданном
   `CLICKIT_DB_URL`; публикация сценария — `python scripts/cloud_publish.py
   publish <файл.acl.json>` (URL и ключ из `--url`/`--api-key` или env
   `CLICKIT_CLOUD_URL`/`CLICKIT_API_KEY`). Тесты сервиса с покрытием —
   `python -m pytest tests/service --cov` (порог 80 %); на реальном
   PostgreSQL — `CLICKIT_TEST_DB_URL=postgresql+psycopg://…`, как в job
   `service-tests`.
5. **M8 — наблюдаемость** (`plans/M8-observability.md`): следующая веха; сначала
   JSON-логи и `/metrics`, затем Grafana/Loki/Tempo, алерты, SLO и runbook.
6. **M9–M10 — инфраструктура и доставка** (`plans/M9-infrastructure.md`,
   `plans/M10-delivery.md`): после M7 и M6 T3.2; Terraform → k3s/Helm/TLS →
   CD staging/prod с откатом и DORA.
7. **M11 — безопасность и устойчивость** (`plans/M11-security-resilience.md`):
   после M10; сканирование/SBOM, нагрузка, бэкапы, chaos, учебный инцидент.
8. **Продуктовый backlog (после M5):** условия `if`/`while` с чтением экрана,
   `recorder.py`, пикер координат в блоке, библиотека шаблонов, локализация
   RU+EN; спайк `PostMessage` — опционально.

### Материалы для GitHub-репозитория (About)

- **Описание (EN, основное):** `🧰 Windows auto-clicker with visual block scripting — snap blocks together to build click scenarios, no coding required. Python + PySide6 + Blockly.`
- **Описание (RU, альтернатива):** `Автокликер для Windows с визуальным программированием: сценарии кликов собираются из блоков, как конструктор — без кода.`
- **Topics:** `autoclicker, auto-clicker, automation, blockly, visual-programming, no-code, python, pyside6, qt, windows, mouse, macro, clicker`

---

## Известные проблемы / вопросы

- [x] Выбрать конкретные версии PySide6 и QtWebEngine (тяжёлая зависимость,
      нужен план Б на случай проблем со сборкой PyInstaller).
      (✅ 2026-10-28: PySide6 6.12.0 + PyInstaller 6.22.3 собираются и
      запускаются; план Б не понадобился.)
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
- [x] Консольные логи с русским текстом в `cmd` могут отображаться в кракозябрах
      (кодировка консоли Windows). Лечится настройкой UTF-8-потока в логировании — M5.
      (✅ 2026-10-28: `setup_logging` переводит консольный поток в UTF-8,
      журнал пишется в UTF-8.)
- [ ] **Условия в сценариях (`if`, `loop while`) — после 1.0.0:** в схеме IR v1
      тип `if` зарезервирован, интерпретатор выдаёт понятную ошибку; редактор M4
      намеренно не показывает эти блоки. Для реальных условий понадобится
      чтение экрана (`pixel()`) — отдельное решение.
- [ ] **`recorder.py` (запись действий мыши в IR) отложен** — после 1.0.0:
      нужен режим записи и защита от самозаписи кликов.
- [ ] **PyInstaller + QtWebEngine (M5):** `resources/blockly/` целиком
      (JS, `msg/`, `media/`) включён в `datas`, NOTICE об Apache-2.0/LGPL
      копируется рядом. Обе сборки локально запускаются и пишут журнал;
      **финальный смоук на чистой Windows** (без Python) — в шагах релиза.
- [ ] **Размер и старт onefile:** ~220 МБ, первый и повторные запуски
      на тестовой машине занимают ~58 с (распаковка QtWebEngine во временный
      каталог + антивирус). Поэтому основной релиз — onedir-архив (`~2 с`),
      onefile остаётся альтернативой для «одного файла». Если понадобится —
      рассмотреть исключение неиспользуемых Qt-модулей.
- [ ] **Web-тесты и QtWebEngine:** offscreen-тесты требуют
      `QTWEBENGINE_DISABLE_SANDBOX=1` и `QTWEBENGINE_CHROMIUM_FLAGS=--disable-gpu`;
      при недоступном Chromium смоук отключается `CLICKIT_SKIP_WEB=1`.
      Реальный рендер Blockly проверен на приёмке M4 (2026-10-27).
- [x] **Docker Desktop и Windows-контейнеры (T0.1, M6):** установщик по
      умолчанию ставит Docker Desktop без компонента Windows-контейнеров
      (`"noWindowsContainers": true` в `C:\ProgramData\DockerDesktop\install-settings.json`),
      из-за чего `DockerCli.exe -SwitchWindowsEngine` падает с
      `windows containers have been disabled for this installation`.
      (✅ 2026-10-31: компонент доустановлен перезапуском инсталлятора,
      потребовалась перезагрузка Windows; после неё переключение движка
      и `servercore:ltsc2022` работают — isolation=hyperv. Переключение из
      неэлевированного процесса невозможно. ✅ 2026-10-31 (T1.1): при работающем
      Docker Desktop `docker context use desktop-linux` переключает движок
      из обычного терминала без прав администратора.)
- [ ] **Docker Desktop сам возвращается на Windows-контейнеры (T1.1, M6):**
      после успешного переключения на `desktop-linux` и работы с Linux-образом
      движок снова оказался `windows` — Linux-образ «пропадает»
      (`no matching manifest for windows(...)`, `pull access denied`).
      Перед docker-командами проверять `docker context ls` и выполнять
      `docker context use desktop-linux`; образ `clikit-test:local` остаётся
      в Linux-движке. В CI (ubuntu-раннер) проблемы нет.
- [ ] **Windows-контейнеры: legacy-билдер и пути (T3.1, M6):** Docker Desktop
      в режиме Windows-контейнеров собирает **без BuildKit** — фильтрация
      контекста по `COPY` не действует, без `.dockerignore` в контекст уходит
      `dist/` (~1 ГБ). CLI нормализует `WORKDIR C:\work` в `C:work` и падает
      с «invalid absolute path» → в Dockerfile пути через `/` (`C:/work`),
      монтирование тоже `-v "<путь>:C:/work"`. В контейнере не резолвится
      `www.nuget.org` (CNAME через trafficmanager) — Python качается с
      `api.nuget.org/v3-flatcontainer/...`. VC++ redist не нужен: PySide6
      несёт `msvcp140`/`vcruntime140`. Переключение движка:
      `docker context use desktop-windows`/`desktop-linux`, сборка —
      `docker buildx use desktop-windows` (иначе BuildKit берёт Linux-билдер
      и падает с `no match for platform`).
- [ ] **Docker Hub: единичные `EOF` при pull (T0.1, M6):** через прокси
      Docker Desktop (`http.docker.internal:3128`) скачивание слоёв с
      `production.cloudfront.docker.com` иногда обрывается с `EOF`;
      повтор `docker pull` проходит. В CI не считать единичный `EOF`
      фатальной ошибкой (ретраи при cold-pull).
- [x] Ручная приёмка M1: реальные клики и F5/F6/fail-safe на машине пользователя
      (✅ 2026-10-24: 100/100 кликов, все хоткеи работают; автотесты хоткеи
      не проверяют: `pynput.GlobalHotKeys` с версии 1.8.2 игнорирует
      injected-события, поэтому синтетические нажатия из тестов не срабатывают).
- [ ] Античит-риски: документировать, что проект предназначен для
      некоммерческого/офлайн-использования. (✅ частично: дисклеймер добавлен в README)
- [x] Выбрать лицензию и добавить файл `LICENSE` до публикации на GitHub.
      (✅ 2026-10-23: **MIT**, правообладатель Danil Momot, файл `LICENSE` создан,
      ADR №6 в `AI_CONTEXT.md`; ✅ 2026-10-28: `packaging/NOTICE.txt`
      о LGPL/Apache/BSD копируется рядом с `.exe`.)
- [x] Переименовать локальную папку `AutoClicker` → `ClicKit` и создать remote `ClicKit`.
      (✅ 2026-10-23: папка уже `ClicKit`, remote `origin` → `github.com/AkaDaka1/ClicKit`.)
