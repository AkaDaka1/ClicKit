# ClicKit Cloud — запуск и эксплуатация

> Практическое руководство по сервису ClicKit Cloud (M7). Нормативный контракт
> HTTP API — [`docs/api.md`](api.md); здесь — зачем сервис нужен, как поднять
> его с чистой машины, как публиковать сценарии и что делать при сбоях.

## 1. Зачем ClicKit Cloud

ClicKit — полностью локальное Windows-приложение: простой режим, блочный
редактор и запуск сценариев работают без сети. ClicKit Cloud — **опциональный
серверный слой**, который дополняет продукт двумя функциями:

| Функция | Что даёт пользователю |
|---|---|
| **Обмен сценариями** | `.acl.json` публикуется по HTTP и скачивается по `id`. Скачанный файл открывается в блочном редакторе и запускается без изменений. |
| **Crash-отчёты** | Приложение (или CLI) отправляет версию, ОС, хэш ошибки и трассировку. Сервер вырезает домашние пути и хранит отчёт 30 дней — без аккаунтов, IP и имён пользователей. |

Сервис **не заменяет** desktop-приложение и **не переносит GUI в контейнер**.
Desktop остаётся работоспособным без сети: недоступность Cloud — это ошибка
отдельной команды публикации, а не отказ приложения (ADR №36).

Ключевое свойство: сервис валидирует IR тем же кодом `core.ir.schema`, что и
desktop (ADR №37). Опубликовать «исполняемый код» или сценарий неизвестного
типа нельзя — принимается только знакомый IR `.acl.json` v1.

```
┌──────────────────────┐   .acl.json    ┌───────────────────────┐
│ ClicKit (desktop)    │ ─────────────► │ ClicKit Cloud         │
│ редактор, исполнение │ ◄───────────── │ FastAPI + PostgreSQL  │
└──────────────────────┘   download     └───────────┬───────────┘
          │ CLI: scripts/cloud_publish.py           │ Alembic
          └─────────────────────────────────────────┘
```

### Что сервис не делает (границы M7)

- нет аккаунтов, OAuth, квот и модерации контента — запись защищена одним
  статическим ключом;
- нет rate limit и anti-abuse (M11);
- нет GUI-кнопки «Опубликовать» — публикация из CLI;
- нет облака, домена и TLS (M9), метрик и алертов (M8), CD (M10);
- нет S3/CDN, версий сценариев, поиска и `PATCH`.

## 2. Что понадобится

| Вариант | Требования |
|---|---|
| **Рекомендуемый: Docker Compose** | Docker Desktop (Linux-контейнеры) с Compose v2; Python на хосте не нужен. |
| Для CLI публикации | Python 3.11+ и пакет `httpx`; сам сервис может работать в Docker. |
| Разработка без Docker | Python 3.11+, PostgreSQL 16 (локально или в контейнере). |

Проверка Docker:

```powershell
docker version
docker compose version
```

Если движок выключен, запустите Docker Desktop и дождитесь статуса
«Engine running». Сервис использует Linux-образы; компонент Windows-контейнеров
для него не требуется.

## 3. Быстрый старт с чистой машины

Все команды ниже выполняются из корня репозитория. В PowerShell используется
`Copy-Item` и `curl.exe` (встроенный `curl` — это алиас `Invoke-WebRequest`);
в bash/macOS/Linux — `cp` и обычный `curl`.

### 3.1. Клонирование и настройки

```powershell
git clone https://github.com/AkaDaka1/ClicKit.git
cd ClicKit
Copy-Item .env.example .env
```

Сгенерируйте ключ и пароль (любая случайная строка от 16 символов подойдёт):

```powershell
[guid]::NewGuid().ToString('N')   # ключ API
[guid]::NewGuid().ToString('N')   # пароль PostgreSQL
```

Откройте `.env` (`notepad .env`) и заполните:

```dotenv
CLICKIT_API_KEY=<ключ записи, ≥ 16 символов>
POSTGRES_PASSWORD=<пароль PostgreSQL>
CLICKIT_ADMIN_API_KEY=
CLICKIT_API_PORT=8000
CLICKIT_LOG_LEVEL=INFO
```

- `CLICKIT_API_KEY` обязателен: без него сервис не стартует (fail-closed).
- `POSTGRES_PASSWORD` обязателен. Используйте буквы и цифры: символы
  `@ : / ? # %` ломают URL подключения.
- `CLICKIT_ADMIN_API_KEY` необязателен. Если заполнить, удалять сценарии
  сможет только этот ключ, а ключ записи получит 403.
- `.env` исключён из Git; в репозитории лежит только `.env.example`.

### 3.2. Запуск

```powershell
docker compose -f docker-compose.cloud.yml up -d --build
docker compose -f docker-compose.cloud.yml ps --all
```

Первая сборка образа занимает несколько минут. Compose поднимает три сервиса:

| Сервис | Роль |
|---|---|
| `db` | PostgreSQL 16 с томом `pgdata` и healthcheck `pg_isready`. |
| `migrate` | Одноразовая задача: `alembic upgrade head`. API стартует только после её успешного завершения. |
| `api` | FastAPI/uvicorn на порту `CLICKIT_API_PORT` (по умолчанию 8000). |

Ожидаемый признак готовности — `api` в состоянии `healthy`, `migrate` —
`exited (0)`, `db` — `healthy`.

### 3.3. Проверка

```powershell
curl.exe -s http://localhost:8000/healthz
curl.exe -s http://localhost:8000/readyz
curl.exe -s http://localhost:8000/version
```

```json
{"status":"ok","service":"clikit-cloud","version":"0.1.0"}
{"status":"ready","checks":{"database":"ok"}}
{"service":"clikit-cloud","version":"0.1.0","git_sha":"local","built_at":"","ir_format_version":1}
```

- `/healthz` — liveness, не обращается к БД;
- `/readyz` — readiness: 200 при доступной БД и 503 без неё (детали — только
  в журнале);
- `/docs` — интерактивная OpenAPI-документация, `/openapi.json` — схема.

### 3.4. Публикация и скачивание

CLI требует Python 3.11+ (сервис при этом остаётся в Docker):

```powershell
python -m pip install httpx
$env:CLICKIT_CLOUD_URL = "http://localhost:8000"
$env:CLICKIT_API_KEY = "<ключ из .env>"

python scripts/cloud_publish.py publish resources/examples/click_pause_loop.acl.json
python scripts/cloud_publish.py list
python scripts/cloud_publish.py download <id> --output downloaded.acl.json
```

`publish` проверяет IR локально до отправки и печатает `id`, `sha256` и URL.
`download` пишет файл атомарно; без `--output` имя берётся из IR
(`<name>.acl.json`). Порядок «скачать → открыть в редакторе → запустить»
ничем не отличается от локального файла: Blockly пересоберёт блоки из IR.

Для повторной отправки используйте `--idempotency-key`: сервер не создаст
дубль в течение 24 часов и вернёт тот же `id`.

### 3.5. Остановка и удаление данных

```powershell
# Остановить, сохранив данные в томе pgdata
docker compose -f docker-compose.cloud.yml down

# Удалить и контейнеры, и данные (необратимо)
docker compose -f docker-compose.cloud.yml down -v
```

### 3.6. Повторный запуск

```powershell
docker compose -f docker-compose.cloud.yml up -d
```

Миграции применяются заново (задача `migrate`), данные из тома `pgdata`
сохраняются. После обновления кода:

```powershell
git pull
docker compose -f docker-compose.cloud.yml up -d --build
```

## 4. Эндпоинты и коды

Полные тела запросов и ответов — [`docs/api.md` §5](api.md#5-эндпоинты).
Краткая карта:

| Метод и путь | Доступ | Назначение |
|---|---|---|
| `GET /healthz` | публичный | liveness без БД |
| `GET /readyz` | публичный | readiness с `SELECT 1` |
| `GET /version` | публичный | версия, git sha, время сборки |
| `GET /metrics` | публичный | заготовка Prometheus (M8) |
| `POST /v1/scenarios` | `X-API-Key` | публикация сценария |
| `GET /v1/scenarios/{id}` | публичный | скачивание `.acl.json`, `ETag` |
| `GET /v1/scenarios` | публичный | список метаданных (`limit`, `offset`) |
| `DELETE /v1/scenarios/{id}` | admin-ключ | удаление |
| `POST /v1/crash-reports` | публичный | приём crash-отчёта |

Ошибки — `application/problem+json` (RFC 7807) с `type`, `title`, `status`,
`detail`, `instance`, `request_id`; у 422 есть `errors` с путями IR.
Основные коды: 401 — нет/неверный ключ; 403 — ключ не даёт права на метод;
404 — нет сценария; 409 — конфликт `Idempotency-Key`; 413 — тело больше 1 МБ;
415 — не JSON; 422 — невалидный запрос/IR; 500 — внутренняя ошибка;
503 — БД недоступна. 429 зарезервирован под rate limit (M11).

### Ограничения

| Параметр | Значение |
|---|---|
| Тело запроса | ≤ 1 МБ (`CLICKIT_MAX_BODY_BYTES`) |
| Узлов в сценарии | ≤ 10 000 |
| Глубина IR | ≤ 32 |
| Ошибок в ответе 422 | ≤ 50 |
| Имя сценария | 1–200 символов |
| Описание | ≤ 2000 символов |
| Crash-отчёт | `app_version` 1–64, `os` ≤ 64, `error_hash` — 64 hex; трассировка ≤ 16 КБ после санитайзера |
| Хранение crash-отчётов | 30 дней (политика; очиститель — M8/M11) |

## 5. CLI

Контракт CLI — [`docs/api.md` §10](api.md#10-клиент-и-cli-контракт-m7-t42).
Справка по любой команде: `python scripts/cloud_publish.py <команда> --help`.

| Команда | Что делает |
|---|---|
| `publish <file.acl.json>` | проверяет IR, публикует; `--name`, `--description`, `--idempotency-key` |
| `download <id>` | скачивает полный IR; `--output` / `-o` |
| `list` | список; `--limit`, `--offset` |
| `delete <id>` | удаляет (нужен ключ с правом удаления) |
| `crash-report <report.json>` | отправляет отчёт; обязательны `app_version` и `error_hash` |

Общие флаги: `--url`, `--api-key`, `--timeout`, `--attempts`. По умолчанию URL
`http://localhost:8000`, ключ — из `CLICKIT_API_KEY`, таймаут 5 с, до 3 попыток
только для 5xx/таймаутов/сети (4xx не повторяются).

Коды выхода: `0` — успех, `2` — ошибка использования, `3` — авторизация,
`4` — не найдено, `5` — невалидные данные (включая 409/413/422), `6` —
сеть/сервер. Это удобно для скриптов:

```powershell
python scripts/cloud_publish.py publish scenario.acl.json
if ($LASTEXITCODE -ne 0) { throw "Публикация не удалась: $LASTEXITCODE" }
```

Пример crash-отчёта (`report.json`):

```json
{
  "app_version": "1.0.0",
  "os": "Windows 11 Pro 23H2",
  "error_hash": "<sha256 сигнатуры ошибки, 64 hex>",
  "traceback": "Traceback (most recent call last): ..."
}
```

```powershell
python scripts/cloud_publish.py crash-report report.json
```

## 6. Проверка и тесты

### 6.1. Проверка живого сервиса

```powershell
curl.exe -s http://localhost:8000/readyz
docker compose -f docker-compose.cloud.yml ps
docker compose -f docker-compose.cloud.yml logs --tail 50 api
```

Остановите БД — `/readyz` должен вернуть 503, а `/healthz` — остаться 200:

```powershell
docker compose -f docker-compose.cloud.yml stop db
curl.exe -s -o NUL -w "%{http_code}`n" http://localhost:8000/healthz   # 200
curl.exe -s -o NUL -w "%{http_code}`n" http://localhost:8000/readyz    # 503
docker compose -f docker-compose.cloud.yml start db
```

### 6.2. Автотесты сервиса

```powershell
python -m pip install -r requirements-service.txt -r requirements-service-test.txt
python -m pytest tests/service --cov
```

По умолчанию тесты используют файловую SQLite; с реальным PostgreSQL 16 —
переменная `CLICKIT_TEST_DB_URL`:

```powershell
$env:CLICKIT_TEST_DB_URL = "postgresql+psycopg://clikit:clikit@localhost:5432/clikit_test"
python -m pytest tests/service --cov
```

Порог покрытия `service/` — 80 % с учётом ветвей (`pyproject.toml`); в CI этим
занимается job `service-tests` на `ubuntu-latest` с сервисным `postgres:16`.

## 7. Разработка без Docker

Понадобится PostgreSQL 16. Быстрый вариант — контейнер только для БД:

```powershell
docker run --name clikit-pg -d `
  -e POSTGRES_USER=clikit -e POSTGRES_PASSWORD=clikit `
  -e POSTGRES_DB=clikit -p 5432:5432 postgres:16

python -m pip install -r requirements-service.txt
$env:CLICKIT_DB_URL = "postgresql+psycopg://clikit:clikit@localhost:5432/clikit"
$env:CLICKIT_API_KEY = "local-development-key-0123456789"
python -m alembic -c service/alembic.ini upgrade head
python -m uvicorn service.app.main:app --port 8000
```

В bash те же переменные задаются через `export`. Схема меняется **только**
миграциями Alembic (ADR №52); сервис не вызывает `create_all`.

Новая миграция после правки `service/app/models.py`:

```powershell
python -m alembic -c service/alembic.ini revision --autogenerate -m "краткое описание"
# просмотрите созданный файл в service/migrations/versions/
python -m alembic -c service/alembic.ini upgrade head
python -m alembic -c service/alembic.ini check   # расхождений быть не должно
```

Сборка production-образа вручную:

```powershell
docker build -f docker/Dockerfile.service -t clikit-service:local .
```

Образ multi-stage, работает не от root (`UID 10001`), имеет `HEALTHCHECK`
по `/healthz` и корректно завершается по SIGTERM (ADR №55).

## 8. Эксплуатация

### 8.1. Журналы

```powershell
docker compose -f docker-compose.cloud.yml logs -f api
docker compose -f docker-compose.cloud.yml logs db
docker compose -f docker-compose.cloud.yml logs migrate
```

Каждый ответ содержит `X-Request-ID`; тот же идентификатор попадает в журнал,
поэтому ошибку пользователя можно найти по `request_id` из problem+json.
Тело crash-отчёта и API-ключи в журнал не пишутся.

### 8.2. Данные и резервная копия

```powershell
# Дамп (cmd /c сохраняет байты; `>` в PowerShell 5.1 пишет UTF-16)
cmd /c "docker compose -f docker-compose.cloud.yml exec -T db pg_dump -U clikit clikit > backup.sql"

# Восстановление в пустую БД
cmd /c "docker compose -f docker-compose.cloud.yml exec -T db psql -U clikit -d clikit < backup.sql"
```

Том `pgdata` переживает `down` и перезапуск; `down -v` удаляет данные.
Порт БД наружу не публикуется — для отладки используйте `psql` внутри
контейнера:

```powershell
docker compose -f docker-compose.cloud.yml exec db psql -U clikit -d clikit
```

Ретеншн crash-отчётов в M7 — политика, а не фоновый процесс. Удалить старые
записи вручную:

```powershell
docker compose -f docker-compose.cloud.yml exec db psql -U clikit -d clikit `
  -c "DELETE FROM crash_reports WHERE created_at < now() - interval '30 days';"
```

### 8.3. Безопасность

- Ключи и пароль — только в `.env`/переменных окружения; `.env` в `.gitignore`.
- Чтение сценариев публичное: кто знает `id`, тот скачает IR. Не публикуйте
  секреты внутри сценариев и описаний.
- Запись защищена ключом, удаление — отдельным admin-ключом (роли не
  иерархичны: admin-ключ не публикует).
- Crash-отчёты санитайзятся (домашние пути → `<пользователь>`), тело не
  логируется, IP приложением не сохраняется.
- Модерации и rate limit в M7 нет — не выставляйте сервис в интернет до M9/M11.

## 9. Диагностика

| Симптом | Причина и решение |
|---|---|
| `CLICKIT_API_KEY ... не задан` при старте | Не заполнен `.env`; задайте ключ ≥ 16 символов. |
| `Задайте POSTGRES_PASSWORD в .env` | Compose не видит `.env`; запускайте из корня репозитория. |
| `port is already allocated` | Порт 8000 занят; измените `CLICKIT_API_PORT` в `.env`. |
| `migrate` завершился с ошибкой | Неверный `POSTGRES_PASSWORD` или БД нездорова; `logs migrate` и `logs db`. |
| `/readyz` → 503 | БД недоступна или ещё стартует; `ps`, `logs db`; `/healthz` при этом 200. |
| `401` на публикации | Нет заголовка `X-API-Key` или ключ не совпадает с `.env`. |
| `403` на удалении | Задан `CLICKIT_ADMIN_API_KEY`, а передан ключ записи — используйте admin-ключ. |
| `413` | Тело больше 1 МБ — уменьшите сценарий или поднимите `CLICKIT_MAX_BODY_BYTES`. |
| `422` | Невалидный IR; пути ошибок — в `errors[].path` (`nodes[2].x`). |
| `curl: (7) Failed to connect` | API не запущен или другой порт; проверьте `compose ps` и `CLICKIT_API_PORT`. |
| `curl` в PowerShell ведёт себя странно | Это алиас `Invoke-WebRequest`; используйте `curl.exe`. |
| CLI: код 6 | Сервис недоступен/5xx после повторов; проверьте `--url` и логи. |

Полезные проверки:

```powershell
docker compose -f docker-compose.cloud.yml config   # проверка подстановки env
docker compose -f docker-compose.cloud.yml ps
curl.exe -s http://localhost:8000/openapi.json | Out-Null   # 200
```

## 10. Связанные документы

- [`docs/api.md`](api.md) — нормативный контракт: эндпоинты, ошибки, лимиты,
  идемпотентность, схема PostgreSQL 16, конфигурация env.
- [`plans/M7-cloud-service.md`](../plans/M7-cloud-service.md) — план вехи,
  граф задач и журнал.
- [`README.md`](../README.md) — обзор продукта и быстрый старт.
- [`AI_CONTEXT.md`](../AI_CONTEXT.md) §3.3 — архитектурные решения (ADR №36–38,
  51–59).
