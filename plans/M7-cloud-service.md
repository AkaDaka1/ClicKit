# M7 — ClicKit Cloud: сервис сценариев

> План создан 2026-11-01. Статус: 🔄 в работе (T0.1 ✅, T1.1 ✅, T1.2 ✅,
> T2.1 ✅, T2.2 ✅ — 2026-11-04).
> Связь: продолжает продукт после M5; не дублирует M6 (Docker-среда тестов,
> образ сборки, GHCR и dev-релизы остаются в M6).

## 1. Цель

Дать ClicKit настоящий серверный слой: HTTP-сервис, в котором пользователи
публикуют и скачивают сценарии `.acl.json`, а приложение отправляет отчёты
о падениях. Это даёт реальный объект эксплуатации: API, база данных,
контейнер, health-проверки, логи и границы ответственности.

Сервис не заменяет desktop-приложение и не переносит GUI в контейнер.
Он дополняет продукт функцией обмена сценариями и телеметрией.

## 2. Критерий готовности

- [ ] `docker compose -f docker-compose.cloud.yml up -d` поднимает API и
      PostgreSQL; `GET /healthz` → 200, `GET /readyz` → 200 при доступной БД
      и 503 при недоступной.
- [ ] `POST /v1/scenarios` создаёт сценарий, `GET /v1/scenarios/{id}` возвращает
      его, `GET /v1/scenarios` отдаёт страницу списка; невалидный IR → 422,
      неизвестный id → 404, повтор с тем же `Idempotency-Key` не создаёт дубль.
- [ ] IR валидируется тем же кодом `core.ir.schema`, что и desktop-приложение;
      тело запроса ограничено 1 МБ; ошибки — в формате `application/problem+json`.
- [ ] Контейнер работает не от root, имеет `HEALTHCHECK`, собирается
      multi-stage и запускается без Python на хосте.
- [ ] `scripts/cloud_publish.py` публикует файл `.acl.json` и скачивает его по id;
      таймауты и retry с backoff проверены тестами с mock-сервером.
- [ ] Автотесты сервиса: не менее 30 тестов, покрытие `service/` ≥ 80%,
      `ruff check` и `ruff format --check` чистые.
- [ ] `docs/cloud.md` и `docs/api.md` описывают запуск, эндпоинты, коды ошибок,
      аутентификацию и ограничения.

## 3. Согласованные параметры

| Параметр | Решение |
|---|---|
| Язык и стек | Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic |
| БД | PostgreSQL 16 в контейнере; том `pgdata` для локального запуска |
| API | Версия `/v1`; JSON; OpenAPI автоматически; ошибки RFC 7807 |
| Аутентификация | `X-API-Key` для записи; чтение сценариев публичное; ключ из env |
| Валидация сценария | Переиспользовать `core.ir.schema.scenario_from_mapping` |
| Размер тела | Не более 1 МБ; лимит проверяется до записи в БД |
| Идентификаторы | UUIDv4; `created_at` / `updated_at` в UTC |
| Идемпотентность | `Idempotency-Key` для `POST /v1/scenarios`, TTL 24 часа |
| Клиент | `httpx` с таймаутом 5 с, 3 попытки, backoff + jitter только для 5xx/timeout |
| Тесты | `pytest`, `pytest-asyncio`, `httpx.AsyncClient`, Postgres в CI-сервисе |
| Деплой | Локально — Docker Compose; облако и Kubernetes — M9 |
| Наблюдаемость | В M7 только заготовки `/metrics` и request id; полноценно — M8 |

## 4. Границы и связь с M6

**Что входит:** сервис, БД, миграции, Docker-образ сервиса, локальный compose,
CLI-клиент, тесты, документация API.

**Что не входит и где делается:**

- публикация образа сервиса в GHCR — M10 (T1.1), после механизма M6 T3.2;
- Kubernetes, домен, TLS, облако — M9;
- метрики, дашборды, алерты, SLO — M8;
- сканирование, SBOM, подпись, нагрузка — M11;
- GUI-кнопка «Опубликовать» — после M7, отдельной задачей; в M7 клиент CLI.

**Правило совместимости:** `core/` не импортирует `service/`, `httpx` и
FastAPI. Сервис может импортировать `core.ir` для валидации — это чистая
доменная логика без GUI. Клиент живёт в `cloud/` и не тянется в `core/`.

**Связь с M6:** M6 T2.1 (job `tests-docker`) уже меняет `ci.yml`; M7 T5.1
добавляет отдельный job `service-tests` только после того, как изменения M6
закоммичены. Если `ci.yml` занят — M7 T5.1 ждёт, остальные задачи M7 не блокируются.

## 5. Модули и интерфейсы

### 5.1. API

| Метод и путь | Назначение | Ответы |
|---|---|---|
| `GET /healthz` | Liveness, без БД | 200 `{"status":"ok"}` |
| `GET /readyz` | Readiness, проверка БД | 200 / 503 |
| `GET /version` | Версия, git sha, время сборки | 200 |
| `GET /metrics` | Заготовка Prometheus (M8) | 200 text/plain |
| `POST /v1/scenarios` | Публикация сценария | 201 / 401 / 413 / 422 / 409 |
| `GET /v1/scenarios/{id}` | Скачивание сценария | 200 / 404 |
| `GET /v1/scenarios?limit=&offset=` | Список сценариев | 200 / 422 |
| `DELETE /v1/scenarios/{id}` | Удаление (по API-ключу) | 204 / 401 / 404 |
| `POST /v1/crash-reports` | Приём отчёта о падении | 202 / 413 / 422 |

Тело `POST /v1/scenarios`:

```json
{
  "name": "click_pause_loop",
  "description": "Пример из resources/examples",
  "scenario": {"version": 1, "name": "demo", "nodes": []}
}
```

Ответ 201: `{"id": "<uuid>", "name": "...", "sha256": "...", "created_at": "..."}`.
Список отдаёт метаданные без полного IR; полный IR — только по id.

### 5.2. Структура каталогов

```
service/
├── app/
│   ├── main.py           # FastAPI, middleware, роутеры
│   ├── config.py         # env-настройки, без секретов в коде
│   ├── version.py        # SERVICE_NAME / SERVICE_VERSION (сборка — из env)
│   ├── db.py             # engine, session, healthcheck
│   ├── models.py         # SQLAlchemy-модели
│   ├── schemas.py        # Pydantic-схемы запросов/ответов
│   ├── scenario_service.py # домен сценариев: хэши, валидация, идемпотентность
│   ├── repository.py     # SqlScenarioRepository (доступ к таблице scenarios)
│   ├── crash_service.py  # домен crash-отчётов: санитайзер PII, валидация, обрезка
│   ├── middleware.py     # BodySizeLimitMiddleware (общий лимит тела)
│   ├── security.py       # API-ключ, сравнение за постоянное время (T3.1)
│   ├── errors.py         # problem+json, обработчики
│   └── api/
│       ├── deps.py       # зависимости маршрутов: сессия БД, UUID, RFC 3339
│       └── v1/           # health.py (системные), scenarios.py, crash_reports.py
├── migrations/           # Alembic
cloud/
├── __init__.py
└── client.py             # httpx-клиент: publish/download, retry, timeout
docker/Dockerfile.service
docker-compose.cloud.yml
requirements-service.txt
docs/api.md
docs/cloud.md
scripts/cloud_publish.py
tests/service/            # API, БД, клиент, идемпотентность (+ conftest.py: БД на тест)
```

Разделение `scenario_service.py` (чистая доменная логика) и `repository.py`
(SQLAlchemy) добавлено в T2.1: бизнес-правила идемпотентности проверяются
без БД, а SQL — на реальной PostgreSQL. `middleware.py` вынесен отдельно,
чтобы лимит тела был общим для всех эндпоинтов, а не только для сценариев.

### 5.3. Модель данных

Уточнена в T0.1; нормативная схема — `docs/api.md` §8.

- `scenarios`: `id uuid pk`, `name text` (1–200), `description text`
  (≤ 2000, `''`), `ir jsonb` (нормализованный IR), `sha256 char(64)`,
  `idempotency_key text null` + `idempotency_body char(64) null`
  (уникальный индекс допускает много NULL — Postgres), `created_at`,
  `updated_at` `timestamptz`; индексы по `sha256`, `idempotency_key`
  (unique) и `created_at DESC`.
- `crash_reports`: `id uuid pk`, `app_version text` (1–64), `os text`
  (≤ 64, `''`), `error_hash char(64)`, `traceback text null` (санитайзер
  домашних путей + обрезка до 16 КБ), `created_at timestamptz`; без имён
  пользователей, путей и IP; индекс по `created_at`.
- Ретеншн crash-отчётов — 30 дней (документируется; очистка — cron/M11).
- `sha256` сценария и `ETag` — хэш канонического JSON
  `Scenario.to_mapping()` (`sort_keys`, `ensure_ascii=False`,
  `separators=(",", ":")`), поэтому скачивание детерминировано.

### 5.4. Ошибки и лимиты

- 401 — нет/неверный `X-API-Key`; 403 — ключ не даёт прав на удаление
  (`CLICKIT_ADMIN_API_KEY` задан, а передан только write-ключ).
- 404 — сценарий не найден; 409 — конфликт `Idempotency-Key` с другим телом.
- 413 — тело больше 1 МБ; 415 — `Content-Type` не JSON; 422 — схема/IR
  невалидны, список путей в `errors`.
- 429 — зарезервировано под rate limit (реализация — M11).
- Все 4xx/5xx — `application/problem+json` с `type`, `title`, `status`,
  `detail`, `instance`, `request_id`.

## 6. Решения (ADR; итоговые формулировки — в `AI_CONTEXT.md` §3.3)

- **ADR №36 — сервис как отдельный слой.** Desktop-приложение остаётся
  локальным и работоспособным без сети; сервис — опциональный backend для
  обмена сценариями и crash-отчётов. Это позволяет контейнеризовать и
  эксплуатировать сервис, не ломая Windows-only GUI.
- **ADR №37 — единая валидация IR.** Сервис не пишет свою схему сценария,
  а вызывает `core.ir.schema.scenario_from_mapping`; формат `.acl.json`
  остаётся одним источником истины.
- **ADR №38 — API-ключ для записи, публичное чтение.** Для пет-проекта
  достаточно статического ключа из env; полноценные пользователи, OAuth и
  квоты — вне M7. Ключ сравнивается за постоянное время, в логи не попадает.

## 7. Граф задач

Статусы: ⬜ не начата · 🔄 в работе · ✅ закрыта · ⛔ заблокирована.

| ID | Задача | Зависимости | Чекпоинт (done = …) | Статус |
|---|---|---|---|---|
| T0.1 | Контракт API и ADR: эндпоинты, коды, лимиты, схема БД | — | `docs/api.md` и этот план согласованы; код не пишется | ✅ |
| T1.1 | Скелет сервиса: FastAPI, config, `/healthz`, `/version` | T0.1 | `uvicorn service.app.main:app` отвечает 200; `ruff` чист | ✅ |
| T1.2 | БД, модели, Alembic, `/readyz` | T1.1 | Postgres поднят, миграции применяются, 200/503 проверены | ✅ |
| T2.1 | CRUD сценариев, валидация IR, идемпотентность, лимит 1 МБ | T1.2 | Тесты 201/200/404/409/413/422; дубль по ключу не создаётся | ✅ |
| T2.2 | Приём crash-отчётов и правила ретеншна | T1.2 | 202, валидация, нет PII; ретеншн описан | ✅ |
| T3.1 | API-ключ, problem+json, `request_id` | T2.1 | 401/403, единый формат ошибок, заголовок `X-Request-ID` | ⬜ |
| T3.2 | `Dockerfile.service`: multi-stage, non-root, healthcheck | T3.1 | Образ собирается, healthy, процесс не от root | ⬜ |
| T4.1 | `docker-compose.cloud.yml`: API + Postgres + том | T3.2 | `up -d` и `down`; данные переживают перезапуск | ⬜ |
| T4.2 | Клиент `cloud/client.py` и `scripts/cloud_publish.py` | T4.1 | Публикация и скачивание против compose; retry/timeout покрыты mock-тестами | ⬜ |
| T5.1 | Тесты сервиса и job `service-tests` в CI | T4.2, M6 T2.1 | ≥ 30 тестов, покрытие ≥ 80%, job зелёный на PR | ⬜ |
| T6.1 | Документация: README, `docs/cloud.md`, `docs/api.md`, ADR | T5.1 | Инструкции воспроизводятся с чистой машины; ADR в §3.3 | ⬜ |

**Уточнение по T3.1 (2026-11-03).** Часть формата ошибок уже реализована в
T2.1: `service/app/errors.py` отдаёт `application/problem+json` со всеми
полями RFC 7807 (включая `request_id` и список `errors` с путями), а
`X-Request-ID` возвращается на ошибках. В T3.1 остаётся: проверка
`X-API-Key` (401/403, `security.py`, write/admin-ключи), валидация и эхо
**входящего** `X-Request-ID` на всех ответах (в т. ч. успешных), единые
обработчики `RequestValidationError`/`HTTPException`/500 и корреляция
`request_id` в журнале.

### Параллелизм (волны)

```
Волна 1: T0.1
Волна 2: T1.1
Волна 3: T1.2
Волна 4: T2.1 ∥ T2.2
Волна 5: T3.1
Волна 6: T3.2 ∥ T4.1
Волна 7: T4.2
Волна 8: T5.1        ← ждёт коммита M6 T2.1, если ci.yml ещё занят
Волна 9: T6.1
```

## 8. Список коммитов

1. `docs: план M7 — сервис сценариев` (T0.1)
2. `feat: скелет ClicKit Cloud` (T1.1)
3. `feat: БД и миграции сервиса` (T1.2)
4. `feat: CRUD сценариев в ClicKit Cloud` (T2.1)
5. `feat: приём crash-отчётов` (T2.2)
6. `feat: API-ключ и единый формат ошибок` (T3.1)
7. `feat: Docker-образ сервиса` (T3.2)
8. `feat: compose для ClicKit Cloud` (T4.1)
9. `feat: клиент публикации сценариев` (T4.2)
10. `test: тесты сервиса и CI-job` (T5.1)
11. `docs: ClicKit Cloud в документации` (T6.1)

## 9. Чек-лист приёмки

- [ ] API отвечает по контракту; OpenAPI открывается и совпадает с `docs/api.md`.
- [ ] Невалидный сценарий отклоняется с 422 и путями ошибок, а не 500.
- [ ] Секреты не в репозитории: только `.env.example` и переменные окружения.
- [ ] Контейнер non-root, healthcheck, корректно завершается по SIGTERM.
- [ ] Тесты сервиса зелёные локально и в CI; `ruff` чистый.
- [ ] README объясняет, зачем сервису нужен ClicKit, и как его запустить.
- [ ] Изменения не затронули поведение desktop-приложения и `core/` без сети.

## 10. Риски и меры

| Риск | Мера |
|---|---|
| Сервис раздувается и отвлекает от desktop | Жёсткие границы: только сценарии и crash-отчёты; всё остальное — «Вне вехи» |
| Дублирование схемы IR | Валидация только через `core.ir.schema`, своих копий нет |
| Тесты требуют Docker/Postgres в CI | Job `service-tests` на `ubuntu-latest` с сервисом `postgres:16`; Windows-матрица не трогается |
| Секреты попадают в логи/репозиторий | Ключ только из env, маскирование, `.env` в `.gitignore`, gitleaks — M11 |
| Конфликт с незакоммиченным M6 T2.1 | T5.1 ждёт коммита; остальные задачи M7 не блокируются |

## 11. Журнал задач

| Дата | Задача | Результат | Commit |
|---|---|---|---|
| 2026-11-01 | — | План создан, границы с M6 зафиксированы | — |
| 2026-11-02 | T0.1 | Контракт API создан — `docs/api.md` (общие соглашения, авторизация по ключам write/admin и fail-closed, `X-Request-ID`/`Idempotency-Key`/`ETag`, RFC 7807 с URN-типами, 9 эндпоинтов с примерами, правила валидации IR через `core.ir.schema`, лимиты, семантика идемпотентности на 24 ч, схема БД Postgres 16, env-конфигурация, интерфейс `cloud/client.py` и CLI с кодами выхода). План §5.3/5.4 уточнён под контракт (хэш тела идемпотентности, индексы, санитайзер traceback, 415). Код не писался | `b42d792` |
| 2026-11-02 | T1.1 | Скелет сервиса: `service/app/{main,config,version,schemas}.py`, `api/v1/health.py` (`/healthz`, `/version`, `/metrics`), `requirements-service.txt`; настройки только из env, проверка при старте в `lifespan` (без `CLICKIT_API_KEY` процесс завершается с `ServiceConfigError` — fail-closed), `ir_format_version` берётся из `core.ir.nodes`. Проверено: `uvicorn service.app.main:app --port 8010` → `/healthz` 200, `/version` 200 (git sha из env), `/metrics` 200 `text/plain; version=0.0.4`, `/openapi.json` 200; запуск без ключа — `Application startup failed`. Тесты: 15 новых (`tests/service/`), всего 289 passed; `ruff check`/`format --check` чисто | — |
| 2026-11-02 | T1.2 | БД и миграции: `service/app/db.py` (`Database`: engine, `session`/`session_scope`, `check()` = `SELECT 1`, `dispose`, таймаут соединения 5 с), `service/app/models.py` (`scenarios`, `crash_reports` по `docs/api.md` §8, CHECK/индексы, `ux_scenarios_idempotency_key`), Alembic (`service/alembic.ini`, `service/migrations/env.py` + `versions/0001_initial_schema.py`, URL только из `CLICKIT_DB_URL`); `CLICKIT_DB_URL` стал обязательным (fail-closed), engine живёт в `lifespan`; `/readyz` — 200 `{"status":"ready","checks":{"database":"ok"}}` / 503 `unavailable` без деталей. Проверено на `postgres:16` в Docker (порт 55432): `upgrade head` → таблицы и `alembic_version=0001`, `alembic check` — без расхождений, `downgrade base`/`upgrade head` повторяются, живой `uvicorn` отдаёт 200, при остановленной БД — 503 при `/healthz` 200, после старта БД — снова 200. Тесты: 35 в `tests/service/` (всего **309 passed**), `ruff check`/`format --check` чисто | — |
| 2026-11-03 | T2.1 | CRUD сценариев: `service/app/{scenario_service,repository,errors,middleware}.py`, `api/v1/scenarios.py`, `api/deps.py`; `POST /v1/scenarios` (201 с `Idempotency-Key`, replay, 409, 413, 415, 422), `GET /v1/scenarios/{id}` (200 с `ETag`, 304 weak/strong), `GET /v1/scenarios` (пагинация, `created_at DESC`), `DELETE` (204/404); `BodySizeLimitMiddleware` (общий слой до разбора, `CLICKIT_MAX_BODY_BYTES`); `ScenarioRepository` с обработкой `IntegrityError` (гонка); валидация IR через `core.ir.schema` (ADR №37). Проверено: живой `uvicorn` + PostgreSQL 16 (Alembic-миграция `0001`), все эндпоинты, ETag, replay, конфликт, лимиты, problem+json. Тесты: 113 service (SQLite + PostgreSQL 16), всего **387 passed**; `ruff` чисто. Commit `83f9585` | `83f9585` |
| 2026-11-04 | T2.2 | Приём crash-отчётов: `service/app/crash_service.py` (валидация `app_version` 1–64 / `os` ≤64 / `error_hash` 64 hex с нормализацией, санитайзер домашних путей `C:\Users\*`, `/home/*`, `/Users/*` → `<пользователь>`, обрезка traceback до 16 384 символов), `api/v1/crash_reports.py` (`POST /v1/crash-reports` — 202 `{id, received_at}`, публичный без `X-API-Key`, ошибки 415/422 problem+json со списком `errors`, тело не логируется), `CrashReceipt` в `schemas.py`, регистрация роутера в `main.py`; ретеншн 30 дней документирован (§5.9, очиститель — M8/M11). Лимит тела наследуется от общего `BodySizeLimitMiddleware`. Тесты: 23 новых в `tests/service/test_crash_reports_api.py` (валидация, PII-санитайзер для трёх ОС, обрезка, 415/413/422, OpenAPI), всего 136 service и **410 passed** полным прогоном; `ruff check`/`format --check` чисто | `000be31` |

## 12. Вне вехи (сознательно)

- GUI-интеграция публикации, аккаунты, OAuth, квоты, модерация контента.
- S3 для больших файлов, CDN, версионирование сценариев.
- Полноценный rate limit и anti-abuse (M11).
- Kubernetes/TLS/облако (M9), наблюдаемость (M8), CD (M10).




