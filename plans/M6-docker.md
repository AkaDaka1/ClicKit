# План M6 — DevOps: Docker + тестовые релизы

> Рабочий план (каталог `plans/` — часть репозитория, планы публичны). Создан 2026-10-31, параметры
> согласованы с пользователем.
>
> **Способ запуска (новая практика, см. `AGENTS.md`):** пользователь в разных
> сессиях запрашивает отдельную задачу по ID («выполни T1.2» / «выполни
> следующую доступную задачу»). Агент работает только над запрошенной задачей
> и только если все её зависимости закрыты, затем обновляет статус в этом
> файле и `PROGRESS.md`.

---

## 1. Цель

Воспроизводимая контейнерная инфраструктура вокруг CI/CD Windows-only продукта:

1. Полный прогон автотестов в Linux-контейнере (локально и в CI).
2. Зафиксированное окружение сборки `.exe` — Windows-контейнерный образ.
3. Публикация обоих образов в GHCR (теги `<sha>`/`latest`/`dev`).
4. Механизм «dev-билда»: тестовый релиз-артефакт по пушу в ветку (аналог
   «деплоя на dev» для desktop-приложения).

## 2. Критерий готовности вехи

- [x] `docker compose run test` локально — все тесты (274+) зелёные.
- [x] CI на PR: `lint` + `tests` (Windows 3.11–3.13) + `tests-docker` (Linux) — зелёно
      (PR #2, run 41317645348).
- [x] Push в `master` → `ghcr.io/akadaka1/clikit-test` и
      `ghcr.io/akadaka1/clikit-build-win` с тегами `latest` и `<sha>`.
- [x] Dry-run `release.yml` (`workflow_dispatch`, publish=false) — сборка
      текущего `master` в контейнере, проверка версии переданного тега и смоук
      зелёные, артефакты сохранены.
- [x] Ручной запуск `dev-release.yml` (branch=master) → draft GitHub Release
      «dev» с `ClicKit-win64.zip` + `SHA256SUMS.txt` + `NOTICE.txt`; повторный
      запуск обновляет (clobber), а не дублирует.
- [x] Документация: ADR №33–35 в `AI_CONTEXT.md` §3.3, §2/§3.2, секция
      «DevOps / Docker» в `README.md`, запись в `PROGRESS.md`.

## 3. Согласованные параметры (решения пользователя, 2026-10-31)

| Параметр | Решение |
|---|---|
| Объём | Полный стек: тестовый образ + образ сборки + GHCR + CI + dev-релизы |
| Linux-тесты в CI | **Параллельный job**, Windows-матрица 3.11–3.13 не трогается |
| Dev-ветка | Долгоживущей ветки **нет**: только механизм (`dev-release.yml` + тег `dev` у образов); ветка создаётся при необходимости (M7+) |
| Docker Desktop | Установлен вместе с WSL2 (2026-10-31); по умолчанию — Linux-контейнеры (WSL2 backend) |
| Имена образов | `ghcr.io/akadaka1/clikit-test` (linux/amd64), `ghcr.io/akadaka1/clikit-build-win` (windows/amd64) |
| Теги образов | `master` → `<sha>` + `latest`; `dev` → `dev` |
| Порядок вех | Dry-run релиза **1.0.0** (`Run workflow`, tag `v1.0.0`) — до T4.1, чтобы провалидировать текущий `release.yml` до перестройки |

## 4. Модули и интерфейсы

### 5. Модули и интерфейсы
- `FROM mcr.microsoft.com/windows/servercore:ltsc2022`.
- Установка Python 3.11 из **NuGet-пакета** `python/3.11.9` (самодостаточная
  распаковка: python.exe, Lib, DLLs, pip; без MSI-мастера и правки PATH
  установщиком). Официального Python-образа для Windows нет, а MSI-установщик
  в servercore требует больше обвязки. Версия — ARG `PYTHON_VERSION`.
- `pip install -r requirements.txt -r requirements-build.txt` отдельным слоем
  (код правится чаще, чем зависимости). VC++ redist не нужен: PySide6
  приносит `msvcp140.dll`/`vcruntime140.dll` с собой.
- Исходники копируются **явным списком** (`app/ bridge/ core/ gui/ packaging/
  resources/ scripts/` + `requirements*.txt`) вместо `COPY . /work`:
  в контекст не попадают `dist/` (~230 МБ), `build/`, `.git/` и кэши, и
  задача не зависит от `.dockerignore`, который создаётся в T1.1 (T3.1 и T1.1
  идут в одной волне, но в разных сессиях). При релизной сборке каталог
  всё равно монтируется поверх (`docker run -v <workspace>:C:\work`).
- `WORKDIR C:\work`, `ENV PYTHONUTF8=1 PYTHONIOENCODING=utf-8`.
- ENTRYPOINT: `C:\Python311\python.exe scripts\build_exe.py` (аргумент `--zip`
  передаётся при `docker run`).

### 4.4 `.dockerignore` (новый; создан в T3.1)
- `.git/`, `.venv/`, `venv/`, `__pycache__/`, `*.pyc`, `.pytest_cache/`,
  `.ruff_cache/`, `reports/`, `dist/`, `build/`, `plans/`, `.github/`,
  `*.zip`, `docker/` — не входит в контекст сборки (Dockerfile указывается
  явно через `-f`).
- **Факт (T3.1):** Windows-движок Docker Desktop собирает образом
  **legacy-билдером без BuildKit**, поэтому фильтрация контекста по `COPY`
  не работает и `.dockerignore` обязателен уже сейчас (в рабочей копии
  `dist/` занимает ~1 ГБ). Файл один на обе задачи волны T1.1∥T3.1:
  T1.1 использует его для Linux-образа, T3.1 — для Windows-образа.

### 4.5 `.github/workflows/docker.yml` (новый)
- `name: Docker images`; `on: push: branches [master, dev]`, `workflow_dispatch`.
- `permissions: contents: read, packages: write`.
- Job `build-test` (`ubuntu-latest`): `docker/login-action@v3` (GITHUB_TOKEN)
  → `docker/build-push-action@v6` (context `.`, file `docker/Dockerfile.test`,
  tags: `master` → `latest`+`<sha>`, `dev` → `dev`; `push: true`).
- Job `build-win` (`windows-latest`): Windows engine использует совместимую
  последовательность `docker build` + `docker push` с `docker/Dockerfile.build-win`
  и `clikit-build-win`; `build-push-action` здесь не применяется, потому что
  runner не предоставляет Buildx для legacy Windows-контейнеров.
- Jobs независимы → идут параллельно.

### 4.6 `ci.yml` (изменения)
- Новый job `tests-docker` (`ubuntu-latest`, параллельно с `lint`/`tests`,
  `needs: []`): образ собирается **из контекста PR** (`docker build -f
  docker/Dockerfile.test`), затем `docker run` с env из 4.1 и
  `python -m pytest -q --junitxml=reports/junit.xml`; JUnit-артефакт при
  падении (как в `tests`).
- Решение: в CI образ из PR-контекста, а не из GHCR — проверка отражает
  содержимое PR, а не чужой билд.
- Существующие job `lint`, `tests`, `package` не меняются.
- **Реализация (T2.1):** `docker build -f docker/Dockerfile.test -t clikit-test:ci .`
  (тег обязателен: без `-t` образ остаётся безымянным и `docker run` его не
  найдёт), `mkdir -p reports`, `docker run --rm --init` с
  `QT_QPA_PLATFORM=offscreen`, `QTWEBENGINE_DISABLE_SANDBOX=1`,
  `QTWEBENGINE_CHROMIUM_FLAGS=--disable-gpu`, bind mount `reports/` и
  аргументами `-q --junitxml=reports/junit.xml` (ENTRYPOINT образа —
  `xvfb-run … python -m pytest`, см. T1.2); при падении выгружается
  артефакт `junit-docker`.

### 4.7 `release.yml` (изменения, T4.1)
- Job `build` (`windows-latest`) переходит на контейнерную сборку:
  `docker build -f docker/Dockerfile.build-win -t clikit-build:rel .` →
  `docker run -v <workspace>:/work clikit-build:rel python scripts/build_exe.py --zip`
  → `verify_release.py --smoke` выполняется на хосте раннера (offscreen).
- **Решение:** ключ `container:` с динамическим тегом не используется
  (тег статичен в YAML; `latest` даёт race при движении `master`).
  Сборка — через `docker run` из образа, собранного из текущего коммита.
- Остальные job (`ci`, `publish`) не меняются.

### 4.8 `dev-release.yml` (новый)
- `on: push: branches [dev]`, `workflow_dispatch` (input `branch`, default
  `master`).
- Job `ci`: `uses: ./.github/workflows/ci.yml` (workflow_call).
- Job `dev-build` (`needs: ci`, `windows-latest`): checkout указанного ref →
  setup-python → pip install → `build_exe.py --zip` →
  `verify_release.py --smoke` → публикация:
  - если релиз с тегом `dev` существует: `gh release upload dev ... --clobber`
    + `gh release edit dev` (title «ClicKit dev build», notes = sha + дата,
    `--draft`);
  - иначе: `gh release create dev ... --draft`.
- `permissions: contents: write` (для создания/обновления релиза и тега).
- Тег `dev` у Docker-образов обеспечивает `docker.yml` (push в `dev`).

## 5. Граф задач

Статусы: ⬜ не начата · 🔄 в работе · ✅ закрыта (с commit) · ⛔ заблокирована.

| ID | Задача | Зависимости | Чекпоинт (done = …) | Статус |
|---|---|---|---|---|
| T0.1 | Проверка Docker на машине | — | `docker run hello-world`, `docker compose version`; Windows-контейнер: `docker run --rm mcr.microsoft.com/windows/servercore:ltsc2022 cmd /c echo ok` (переключить движок на Windows containers и обратно) | ✅ (2026-10-31: hello-world, compose v5.6.1, servercore → `ok`, isolation=hyperv; движок вернули на Linux; компонент Windows-контейнеров доустановлен + перезагрузка) |
| T1.1 | `docker/Dockerfile.test` + `.dockerignore` + `docker-compose.yml`; первая сборка | T0.1 | Образ собирается; `docker compose run test` стартует (зелёные тесты пока не обязательны) | ✅ (2026-10-31: `clikit-test:local` собран (421 MB), `docker compose run test` стартует и pytest собирает тесты; `evdev` собирается из исходников → в слой pip временно ставятся `gcc`+`libc6-dev`+`linux-libc-dev` и удаляются; файлы без коммита — войдут в коммит T1.2) |
| T1.2 | **Гейт-спайк:** довести тесты в контейнере до зелёного (системные библиотеки, Xvfb, QtWebEngine) | T1.1 | 272+ тестов зелёно в контейнере; commit `fix: зелёные тесты в docker-контейнере` | ✅ (2026-11-01: `Dockerfile.test` — полный список apt-пакетов Qt/WebEngine/X11/XCB, ENTRYPOINT `xvfb-run --auto-servernum python -m pytest` (pynput/pyautogui требуют `DISPLAY` даже при offscreen); в `tests/conftest.py` — `pytest_sessionfinish` + `pytest_unconfigure` на Linux закрывают QtWebEngine и выходят через `os._exit`, иначе PySide6 падает на финализации (`bool_dealloc`) при зелёных тестах. Итог: 274 passed, exit 0, JUnit пишется; commit `5ed9d93`) |
| T2.1 | `ci.yml`: job `tests-docker` | T1.2 | CI на PR зелёный (lint + tests + tests-docker); commit `feat: ci-job автотестов в контейнере` | ✅ (2026-11-01: job `tests-docker` — сборка с тегом `clikit-test:ci` из контекста PR, `docker run --init` с env Qt/WebEngine, `mkdir -p reports` + монтирование, `--junitxml` и артефакт `junit-docker` при падении; **PR #2 — все job зелёные:** lint, tests 3.11/3.12/3.13, tests-docker (68 c), [run 41317645348](https://github.com/AkaDaka1/ClicKit/actions/runs/41317645348); commit `e5225d4`) |
| T3.1 | `docker/Dockerfile.build-win`; локальная сборка (Windows containers, Docker Desktop) | T0.1 | `docker run ... build_exe.py --zip` собирает zip; commit `feat: windows-образ сборки` | ✅ (2026-10-31: образ 5.94 ГБ собран, `docker run --zip` собрал `ClicKit-win64.zip` 230.6 МБ; артефакт прошёл `verify_release.py --smoke` на хосте; попутно создан `.dockerignore`) |
 | T3.2 | `.github/workflows/docker.yml` → GHCR | T1.2, T3.1 | Push в master → оба образа в GHCR (`latest` + `<sha>`); commit `feat: публикация образов в GHCR` | ✅ (2026-11-01: добавлен параллельный Linux/Windows workflow с `docker/login-action`, `docker/metadata-action` и `docker/build-push-action`; для `master` публикуются SHA + `latest`, для `dev` — SHA + `dev`) |
 | T4.1 | `release.yml`: сборка релиза через `docker build` + `docker run` образа сборки | T3.2 | Dry-run `release.yml` (workflow_dispatch, publish=false): CI → сборка в контейнере → смоук → артефакты, всё зелёное; commit `feat: сборка релиза в контейнере` | ✅ (2026-11-01: job `build` собирает `docker/Dockerfile.build-win`, запускает `build_exe.py --zip` с bind mount, затем выполняет host smoke; ручной dry-run собирает текущий `master`, но сверяет версию указанного тега — старый `v1.0.0` не содержит `docker/`; публикация отключается через `publish=false`) |
 | T5.1 | `.github/workflows/dev-release.yml` + rolling draft Release «dev» | T3.2 | Ручной запуск (branch=master) → draft-релиз «dev» с артефактами; второй запуск обновляет через clobber; commit `feat: тестовые релизы (dev)` | ✅ (2026-11-01: workflow вызывает полный CI, собирает и проверяет архив, создаёт или обновляет draft `dev` с `--clobber`; ref выбирается input `branch` или push в `dev`) |
 | T6.1 | Документация: ADR-формулировки в `AI_CONTEXT.md`, §2/§3.2, README «DevOps / Docker», `PROGRESS.md`, `.gitignore` (если появились артефакты) | T2.1, T3.2, T4.1, T5.1 | Документация совпадает с реализацией; commit `docs: docker и dev-релизы в документации` | ✅ (2026-11-01: README, ROADMAP, AI_CONTEXT и PROGRESS синхронизированы; новые артефакты `reports/`, `dist/`, `build/` уже покрыты `.gitignore`) |

### Параллелизм (волны)

```
Волна 1:  T0.1
Волна 2:  T1.1 ∥ T3.1          ← можно в разных сессиях одновременно
Волна 3:  T1.2                 ← гейт для CI-ветки
Волна 4:  T2.1 ∥ T3.2          ← независимы после T1.2/T3.1
Волна 5:  T4.1 ∥ T5.1          ← независимы после T3.2
Волна 6:  T6.1                 ← только после всех фич
```

### Правила запуска задач в сессии

1. Пользователь называет ID задачи (или «следующая доступная»).
2. Агент перечитывает этот файл, проверяет зависимости (все ✅), иначе
   отказывается и называет, что закрыть.
3. Работает только над этой задачей; в конце обновляет строку задачи
   (статус ✅ + commit), дописывает строку в «Журнал задач» (§7) и
   `PROGRESS.md`.
4. Задача без пройденного чекпоинта не помечается ✅.
5. Если работа уводит от плана — сначала правится этот файл (правило
   `AGENTS.md`), потом работа.

## 6. Решения (ADR; в `AI_CONTEXT.md` §3.3 уже внесены как №33–35)

- **ADR №33 — Docker в Windows-only продукте.** Контейнерируется
  инфраструктура разработки (тесты, окружение сборки), а не продукт:
  GUI-приложение не может работать в Linux-контейнере. Linux-тесты
  **дополняют** Windows-матрицу (parity среды разработки, скорость),
  но не заменяют её — целевая платформа остаётся Windows.
- **ADR №34 — Build environment как артефакт.** Окружение сборки `.exe`
  зафиксировано в `docker/Dockerfile.build-win` (servercore + Python 3.11 +
  PyInstaller) и публикуется в GHCR; релизная сборка идёт в этом образе
  (`docker run` из образа текущего коммита). Ключ `container:` с
  динамическим тегом отклонён: тег статичен в YAML, `latest` создаёт race
  при движении `master`. Образ дублирован локально для Docker Desktop.
- **ADR №35 — Тестовые релизы (dev-практика).** Аналог «деплоя на dev»
  для desktop: rolling **draft** GitHub Release «dev» (обновление
  `--clobber`), публикуемый `dev-release.yml` по пушу в ветку `dev` или
  вручную для любого ref. Долгоживущая `dev`-ветка намеренно не создаётся
  (один разработчик; расходимость gitflow без пользы) — ветка создаётся
  при необходимости, механизм уже готов.

## 7. Журнал задач

| Дата | Задача | Результат | Commit |
|---|---|---|---|
| 2026-10-31 | — | План создан, параметры согласованы | — |
| 2026-10-31 | T0.1 | Docker Desktop 4.97.0 (244584), engine 29.9.2, compose v5.6.1, backend WSL2: `hello-world` — «Hello from Docker!», `python:3.11-slim` (3.11.18) тянется и работает (база T1.1 уже в кэше). Windows-часть: Docker Desktop был установлен с `noWindowsContainers: true` → компонент доустановлен переустановкой инсталлятора (`install-settings.json` теперь без флага) + перезагрузка машины; после неё `-SwitchWindowsEngine` → контекст `desktop-windows`, `servercore:ltsc2022` (5.05 GB, isolation=hyperv) → `cmd /c echo ok` = `ok`, exit 0; движок возвращён на Linux (`desktop-linux`, linux/amd64). Попутно: pull'ы из Docker Hub периодически падают `EOF` через прокси `http.docker.internal:3128` — помогает ретрай | — (проверка окружения, без изменений в коде) |
| 2026-10-31 | T3.1 | `docker/Dockerfile.build-win` (servercore:ltsc2022 + Python 3.11.9 из NuGet flat-container + `pip install -r requirements.txt -r requirements-build.txt`, явный `COPY` исходников, `WORKDIR C:/work`, ENTRYPOINT `build_exe.py`) и `.dockerignore` (создан здесь: Windows-движок собирает **legacy-билдером без BuildKit**, фильтрации контекста по `COPY` нет, а `dist/` в рабочей копии ~1 ГБ). Образ `clikit-build-win:local` — 5.94 ГБ; сборка ~25 мин (pip через прокси контейнера 120–750 КБ/с). Проверка чекпоинта: `docker run --rm -v "<копия репозитория>:C:/work" clikit-build-win:local --zip` → `dist/ClicKit-win64.zip` 230.6 МБ (3286 записей, `ClicKit/ClicKit.exe`, `NOTICE.txt`, Blockly в `_internal/resources/`), `SHA256SUMS.txt`; собранный артефакт проверен на хосте `python scripts/verify_release.py --dist … --smoke` — «Проверка релиза пройдена». Найденные особенности окружения: (1) Windows-контейнеры = legacy builder → нужен `.dockerignore`; (2) `WORKDIR C:\work` CLI нормализует в `C:work` («invalid absolute path») → в Dockerfile пути через `/`, bind mount `-v "<путь>:C:/work"`; (3) `www.nuget.org` в контейнере не резолвится (CNAME через trafficmanager), `api.nuget.org`/`pypi.org`/`python.org` — да; (4) VC++ redist в образе не нужен: PySide6 несёт `msvcp140`/`vcruntime140`; (5) движок возвращён на Linux, buildx-билдер `desktop-linux` | `feat: windows-образ сборки` |
| 2026-10-31 | T1.1 | Созданы `docker/Dockerfile.test` (python:3.11-slim, apt-пакеты Qt/WebEngine/Xvfb, pip из `requirements.txt`, `ENTRYPOINT python -m pytest`), `.dockerignore` (VCS, кэши, dist/build/reports, plans, docker/) и `docker-compose.yml` (сервис `test`, env `QT_QPA_PLATFORM=offscreen`, `QTWEBENGINE_DISABLE_SANDBOX=1`, `QTWEBENGINE_CHROMIUM_FLAGS=--disable-gpu`, `init: true`). Образ `clikit-test:local` собран (контент 421 MB). Первая сборка падала дважды: `evdev` (зависимость pynput на Linux) требует сборки из исходников — добавлены временные `gcc`+`libc6-dev`+`linux-libc-dev` (ставятся и удаляются в том же слое, что pip). `docker compose run --rm test` стартует: pytest собирает тесты, 12 ошибок сбора из-за нехватки `libEGL.so.1` и переменной `DISPLAY` — это ожидаемый вход в гейт T1.2 (зелёные тесты не требовались). Попутно: Docker Desktop оказался переключён на Windows-контейнеры — `docker context use desktop-linux` вернул Linux-движок; один pull `python:3.11-slim` повторили из-за `EOF`; после проверки Docker Desktop снова оказался на Windows-контейнерах — перед запуском нужно проверять `docker context ls` (см. §9) | `feat: docker-среда для автотестов` (3877f33; закоммичено по решению пользователя до T1.2 — зелёный прогон остаётся в T1.2) |
| 2026-11-01 | T1.2 | `docker/Dockerfile.test`: apt-список доведён до Qt/WebEngine — добавлены `xauth`, `libtk8.6`, `libegl1`/`libgles2`, `libdrm2`/`libgbm1`/`libxshmfence1`, `libpango-1.0-0`/ATK/AT-SPI, `libcups2`, `libnspr4`, полный набор `libxcb-*`; ENTRYPOINT заменён на `xvfb-run --auto-servernum python -m pytest` — pynput/pyautogui требуют `DISPLAY` даже при `QT_QPA_PLATFORM=offscreen` (иначе 6 ошибок сбора: `failed to acquire X connection`, `KeyError: 'DISPLAY'`). Первый полный прогон: 274 passed за ~8 с, но exit 134 — «Fatal Python error: bool_dealloc» при финализации интерпретатора (PySide6 + QtWebEngine, живые потоки Chromium); закрытие окон и `gc.collect()` в `pytest_sessionfinish` проблемы не решают. Итог: в `tests/conftest.py` два хука — `pytest_sessionfinish` (только Linux и если загружен `PySide6.QtWebEngineCore`: `closeAllWindows`, `DeferredDelete`, `gc`) и `pytest_unconfigure` (`os._exit(exitstatus)` — JUnit и сводка к этому моменту записаны). Финальная проверка: `docker run … clikit-test:local -q --junitxml=reports/junit.xml` → 274 passed, exit 0, `reports/junit.xml` — `tests="274" failures="0"`; на хосте (Windows) `pytest -q` → 274 passed, `ruff check`/`format --check` чисто | `fix: зелёные тесты в docker-контейнере` (5ed9d93) |
| 2026-11-01 | T2.1 | Job `tests-docker` в `ci.yml` переписан: было `docker build -f docker/Dockerfile.test .` без `-t` (образ остаётся безымянным) + `docker run … clikit-test:local python -m pytest -q` (на чистом раннере образа нет, а ENTRYPOINT дал бы двойной `python -m pytest`) — job упал бы на первом же PR. Стало: сборка `-t clikit-test:ci` из контекста PR, `mkdir -p reports`, `docker run --rm --init` с env Qt/WebEngine (`offscreen`, sandbox off, `--disable-gpu`), bind mount `${{ github.workspace }}/reports:/work/reports` и аргументы `-q --junitxml=reports/junit.xml`; при падении — артефакт `junit-docker` (7 дней). Локально та же команда: 274 passed, exit 0; JUnit пишется. Чекпоинт: PR #2 — все job зелёные (lint, tests 3.11/3.12/3.13, tests-docker 68 c), run 41317645348 | `feat: ci-job автотестов в контейнере` (e5225d4) |
 | 2026-11-01 | T3.2 | Добавлен `.github/workflows/docker.yml`: два независимых job на `ubuntu-latest`/`windows-latest`, вход в GHCR через `GITHUB_TOKEN`, публикация `ghcr.io/akadaka1/clikit-test` и `ghcr.io/akadaka1/clikit-build-win` с SHA-тегом и `latest`/`dev` по ветке | рабочая копия |
 | 2026-11-01 | T4.1 | `release.yml` переведён на сборку из `docker/Dockerfile.build-win` через `docker build` + bind-mounted `docker run`; host runner сохраняет smoke-проверку и артефакты, `publish=false` сохраняет dry-run | рабочая копия |
 | 2026-11-01 | T5.1 | Добавлен `.github/workflows/dev-release.yml`: полный reusable CI, ручной ref, сборка/смоук и rolling draft `dev` через `gh release upload --clobber` | рабочая копия |
 | 2026-11-01 | T6.1 | README дополнен разделом DevOps/Docker, план и статусные документы синхронизированы с тремя workflow; локально проверен `git diff --check` | рабочая копия |

## 8. Список коммитов (итог вехи)

1. `feat: docker-среда для автотестов` (T1.1 — 3877f33)
2. `fix: зелёные тесты в docker-контейнере` (T1.2 — 5ed9d93)
3. `feat: ci-job автотестов в контейнере` (T2.1 — e5225d4)
4. `feat: windows-образ сборки` (T3.1 — eed9e5c)
5. `feat: публикация образов в GHCR` (T3.2)
6. `feat: сборка релиза в контейнере` (T4.1)
7. `feat: тестовые релизы (dev)` (T5.1)
8. `docs: docker и dev-релизы в документации` (T6.1)

## 9. Риски и меры

| Риск | Мера |
|---|---|
| QtWebEngine/pyautogui на Linux не стартуют | Итерации над apt-пакетами в T1.2; гейт не пропущен — фазы 2+ не стартуют до зелёного спайка |
| Windows-контейнеры на GH-раннерах медлительны/нестабильны | T3.2/T4.1 используют `windows-latest` (нативная поддержка); fallback T4.1 — вернуть обычный build в `release.yml`, образ остаётся для локальной сборки |
| Cold-pull `servercore` (~3–4 ГБ) в CI | timeout 60 мин на job; при необходимости — `docker pull` warm-up перед build |
| Docker Desktop по умолчанию в Linux-режиме | Для T3.1 переключить движок (`features.windowsContainers=true`), после — вернуть; зафиксировано в чекпоинте T0.1 |
| **Факт (T0.1):** поддержка Windows-контейнеров в Docker Desktop может быть выключена при установке (`noWindowsContainers: true` в `C:\ProgramData\DockerDesktop\install-settings.json`) — `-SwitchWindowsEngine` падает с `windows containers have been disabled for this installation` | Перед T3.1 (и на новых машинах/раннерах) убедиться, что компонент установлен: переустановка инсталлятором + перезагрузка; проверка `docker context ls` → есть `desktop-windows`. Из неэлевированного процесса переключение невозможно — нужны права администратора |
| **Факт (T0.1):** первые попытки `docker pull` падают с `EOF` от `production.cloudfront.docker.com` (прокси `http.docker.internal:3128`) | Ретраить pull (2-я/3-я попытка проходит); в CI учитывать при cold-pull, не считать единичный EOF фатальной ошибкой |
| **Факт (T3.1):** в режиме Windows-контейнеров Docker Desktop собирает **legacy-билдером**: BuildKit недоступен, фильтрация контекста по `COPY` не работает, `dist/` (~1 ГБ) уходит в контекст | `.dockerignore` обязателен (создан в T3.1); образ собирается с `--context desktop-windows`, `docker buildx use desktop-windows` |
| **Факт (T3.1):** `WORKDIR C:\work` в Dockerfile CLI Windows-движка нормализует в `C:work` и падает с «invalid absolute path»; экранирование `"C:\\work"` тоже работает | В Dockerfile пути через `/` (`WORKDIR C:/work`, ENTRYPOINT `C:/Python311/python.exe`); bind mount только как `-v "<путь>:C:/work"` |
| **Факт (T3.1):** в Windows-контейнере не резолвится `www.nuget.org` (CNAME-цепочка через trafficmanager), при этом `api.nuget.org`, `pypi.org`, `files.pythonhosted.org`, `python.org` доступны | Python качается из flat container `api.nuget.org/v3-flatcontainer/python/<версия>/…`; загрузка в 3 попытки (прокси рвёт соединения) |
| **Факт (T1.1):** Docker Desktop после успешного `docker context use desktop-linux` может сам вернуться на Windows-контейнеры — Linux-образ тогда «пропадает» (`no matching manifest for windows(...)` / `pull access denied` для `clikit-test:local`) | Перед docker-командами проверять `docker context ls` и возвращать `docker context use desktop-linux` (переключение из CLI работает без перезапуска и прав администратора). В CI образы linux/amd64 на `ubuntu-latest` — проблема только локальная |
| **Факт (T1.2):** `pynput`/`pyautogui` на Linux требуют `DISPLAY` даже при `QT_QPA_PLATFORM=offscreen` — 6 тестовых модулей не собираются (`failed to acquire X connection`, `KeyError: 'DISPLAY'`) | ENTRYPOINT образа — `xvfb-run --auto-servernum python -m pytest`; `xvfb` и `xauth` в apt-слое. Env Qt/WebEngine передаётся в `docker run` из `docker-compose.yml`/`ci.yml` |
| **Факт (T1.2):** PySide6 + xvfb падает на финализации интерпретатора (`Fatal Python error: bool_dealloc`) после зелёного прогона QtWebEngine-тестов — exit code 134 | В `tests/conftest.py`: на Linux при загруженном `PySide6.QtWebEngineCore` — закрытие окон и `gc` в `pytest_sessionfinish`, затем `os._exit(exitstatus)` в `pytest_unconfigure` (JUnit и сводка уже записаны). На Windows хук не активен |
| Race тегов GHCR в релизе | Обойдён архитектурно (ADR №34: `docker run` из образа коммита, а не `container: latest`) |

## 10. Чек-лист приёмки (дублирует §2, для финальной сессии)

- [x] Локально: `docker compose run test` — зелёно (Linux-контейнеры).
- [x] Локально: `docker build -f docker/Dockerfile.build-win` + `docker run` →
      zip собирается (Windows-контейнеры).
- [x] PR-прогон: три зелёных job (lint, tests, tests-docker).
- [ ] `master`: два образа в GHCR с `latest` + `<sha>`.
- [ ] Dry-run release: артефакты релиза собрана в контейнере.
- [ ] Draft-релиз «dev» существует и обновляется повторным запуском.
- [ ] Документация и ADR актуальны; `ruff check` + `ruff format --check` +
      `pytest` зелёные на `master`.
