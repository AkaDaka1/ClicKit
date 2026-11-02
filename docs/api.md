# ClicKit Cloud — контракт HTTP API

> Версия контракта: **1.0** (M7, задача T0.1). Источник истины для реализации
> `service/` и клиента `cloud/client.py`. Изменения контракта — только через
> правку этого файла и пересогласование плана M7.

## 1. Общие соглашения

- **Base URL:** `http://localhost:8000` локально; путь без префикса, версия —
  в пути (`/v1/...`). Ответы — только `application/json` (и
  `application/problem+json` для ошибок).
- **Кодировка:** UTF-8. Строки сравниваются/тримятся по Unicode-кодовым
  точкам, не по байтам.
- **Время:** все `created_at` / `updated_at` — RFC 3339 в UTC
  (`2026-11-02T10:00:00Z`), в БД — `timestamptz`.
- **Идентификаторы:** UUIDv4.
- **Версионирование API:** мажор в пути (`/v1`). Существующие поля не
  удаляются и не перестают интерпретироваться без повышения версии; новые
  поля — только по повышению `version` контракта либо аддитивно под тем же
  `/v1` (неизвестные клиентом поля игнорируются).
- **OpenAPI:** автоматически на `/openapi.json`, документация — на `/docs`
  (в M7 включены; отключение — конфигурация деплоя, M9).

## 2. Аутентификация и авторизация

| Роль | Методы | Механизм |
|---|---|---|
| Публичный доступ | `GET /healthz`, `/readyz`, `/version`, `/metrics`, `GET /v1/scenarios`, `GET /v1/scenarios/{id}` | без ключа |
| Публикация | `POST /v1/scenarios` | `X-API-Key: <CLICKIT_API_KEY>` |
| Удаление | `DELETE /v1/scenarios/{id}` | `CLICKIT_ADMIN_API_KEY`, если задан; иначе `CLICKIT_API_KEY` |
| Crash-отчёты | `POST /v1/crash-reports` | без ключа (анонимная телеметрия) |

- Заголовок аутентификации: `X-API-Key`. Ключ сравнивается **за постоянное
  время** (`hmac.compare_digest`), в логи и ответы не попадает.
- Отсутствие/неверный ключ на защищённом методе → **401**.
- Ключ не имеет права на метод (админ-ключ задан, а передан только write-ключ,
  и наоборот) → **403**.
- Если `CLICKIT_API_KEY` не задан в конфигурации — сервис **не стартует**
  (fail-closed, секрет не выдумывается).
- Требования к длине ключа: `CLICKIT_API_KEY` и `CLICKIT_ADMIN_API_KEY` —
  от 16 символов; короче — ошибка конфигурации при старте.

## 3. Общие заголовки

| Заголовок | Куда | Правило |
|---|---|---|
| `X-Request-ID` | все ответы | генерируется сервером (UUID4), если клиент не прислал свой; валидный входящий (32–64 символа `[A-Za-z0-9._-]`) пробрасывается; эхо в ответе и `.request_id` в problem+json |
| `Idempotency-Key` | `POST /v1/scenarios` | см. §8; необязательный |
| `ETag` | `GET /v1/scenarios/{id}` | `"<sha256>"`; поддержка `If-None-Match` → 304 |
| `Idempotent-Replay` | `POST /v1/scenarios` | `true` при возврате ранее созданного сценария по тому же ключу |

## 4. Формат ошибок (RFC 7807)

Все 4xx/5xx отдают `Content-Type: application/problem+json` вида:

```json
{
  "type": "urn:clikit:error:validation",
  "title": "Сценарий не прошёл проверку",
  "status": 422,
  "detail": "3 ошибки в теле запроса",
  "instance": "/v1/scenarios",
  "request_id": "f30c…",
  "errors": [
    {"path": "nodes[0].x", "message": "нет обязательного поля 'x'"},
    {"path": "name", "message": "должно быть от 1 до 200 символов"}
  ]
}
```

- `type` — стабильный URN (см. таблицу ниже), `title` — короткий заголовок,
  `status` — HTTP-код, `detail` — человекочитаемая деталь, `instance` — путь
  запроса, `request_id` — корреляция с журналом, `errors` — только для 422
  (список `{path, message}`, до 50 записей).
- Названия полей ошибок IR берутся **напрямую** из
  `core.ir.schema.ValidationIssue` (пути вида `nodes[2].children[0].x`).

### Типы ошибок

| type URN | status | Когда |
|---|---|---|
| `urn:clikit:error:unauthorized` | 401 | нет/неверный `X-API-Key` |
| `urn:clikit:error:forbidden` | 403 | ключ не даёт права на метод |
| `urn:clikit:error:not-found` | 404 | сценарий с таким id не найден |
| `urn:clikit:error:conflict` | 409 | `Idempotency-Key` повторён с другим телом |
| `urn:clikit:error:payload-too-large` | 413 | тело больше лимита (1 МБ) |
| `urn:clikit:error:unsupported-media-type` | 415 | `Content-Type` не `application/json` |
| `urn:clikit:error:validation` | 422 | схема запроса / IR невалидны |
| `urn:clikit:error:unavailable` | 503 | сервис недоступен (БД) или не сконфигурирован |
| `urn:clikit:error:internal` | 500 | неожиданная ошибка сервера |

429 зарезервирован под rate limit (реализация — M11), в M7 не возвращается.

## 5. Эндпоинты

### 5.1. `GET /healthz` — liveness, без БД

200:

```json
{"status": "ok", "service": "clikit-cloud", "version": "0.1.0"}
```

### 5.2. `GET /readyz` — readiness, с проверкой БД

200 при `SELECT 1` успешен:

```json
{"status": "ready", "checks": {"database": "ok"}}
```

503 при недоступной БД:

```json
{"status": "unavailable", "checks": {"database": "error"}}
```

Детали ошибки БД в ответ не попадают (только в журнал).

### 5.3. `GET /version` — версия и сборка

200:

```json
{
  "service": "clikit-cloud",
  "version": "0.1.0",
  "git_sha": "84a7ee4",
  "built_at": "2026-11-02T00:00:00Z",
  "ir_format_version": 1
}
```

`version` — константа `service/app/version.py`; `git_sha`/`built_at` — из env
(`CLICKIT_GIT_SHA`, `CLICKIT_BUILD_TIME`, по умолчанию `"unknown"`/`""`).
`ir_format_version` равен `core.ir.nodes.SCENARIO_VERSION`.

### 5.4. `GET /metrics` — заготовка Prometheus (текст)

200, `Content-Type: text/plain; version=0.0.4`:

```text
# HELP clikit_build_info Сведения о сборке ClicKit Cloud.
# TYPE clikit_build_info gauge
clikit_build_info{version="0.1.0",git_sha="unknown"} 1
```

Полные метрики — M8.

### 5.5. `POST /v1/scenarios` — публикация сценария

Требует `X-API-Key`. Тело (≤ 1 МБ):

```json
{
  "name": "click_pause_loop",
  "description": "Пример из resources/examples",
  "scenario": {"version": 1, "name": "demo", "nodes": []}
}
```

Поля:

| Поле | Тип | Обязательное | Правила |
|---|---|---|---|
| `name` | string | нет | 1–200 символов; по умолчанию — `scenario.name`; если и он пуст → 422 |
| `description` | string | нет | ≤ 2000 символов; по умолчанию `""` |
| `scenario` | object | да | IR-сценарий (см. §6), валидируется `core.ir.schema.scenario_from_mapping` |

**201** — сценарий создан:

```json
{
  "id": "d9f0…-uuid",
  "name": "click_pause_loop",
  "sha256": "ab12…",
  "created_at": "2026-11-02T10:00:00Z",
  "updated_at": "2026-11-02T10:00:00Z",
  "url": "/v1/scenarios/d9f0…-uuid"
}
```

Возможные ошибки: 401, 403 (нет прав), 409 (конфликт идемпотентности, §8),
413 (тело > 1 МБ), 415, 422 (см. §4). Повтор с тем же `Idempotency-Key` —
см. §8.

### 5.6. `GET /v1/scenarios/{id}` — скачивание сценария

200 — полный документ `.acl.json` (валидированный и нормализованный IR):

```json
{"version": 1, "name": "demo", "nodes": [{"type": "click", "x": 100, "y": 200}]}
```

Заголовки: `ETag: "<sha256>"`, `Content-Disposition: attachment; filename="<name>.acl.json"` (имя очищается от управляющих символов). При `If-None-Match` с совпадающим `ETag` → **304** без тела.

Возможные ошибки: 404, 422 (невалидный UUID в пути).

### 5.7. `GET /v1/scenarios?limit=&offset=` — список (метаданные)

Параметры: `limit` (1–100, по умолчанию 20), `offset` (≥ 0, по умолчанию 0).
Сортировка: `created_at` DESC (новые сверху). Полный IR в списке **не**
отдаётся.

200:

```json
{
  "items": [
    {
      "id": "d9f0…-uuid",
      "name": "click_pause_loop",
      "description": "Пример из resources/examples",
      "sha256": "ab12…",
      "created_at": "2026-11-02T10:00:00Z",
      "updated_at": "2026-11-02T10:00:00Z"
    }
  ],
  "total": 42,
  "limit": 20,
  "offset": 0
}
```

`total` — полное число сценариев (независимо от пагинации). Ошибка:
422 (limit/offset вне диапазона).

### 5.8. `DELETE /v1/scenarios/{id}` — удаление

Требует ключ (см. §2). Удаляет строку; повторное удаление → 404.

- **204** — без тела.
- Ошибки: 401, 403, 404, 422 (невалидный UUID).

### 5.9. `POST /v1/crash-reports` — приём отчёта о падении

Публичный (анонимный). Тело (≤ 1 МБ):

```json
{
  "app_version": "1.0.0",
  "os": "Windows 11 Pro 23H2",
  "error_hash": "<sha256 сигнатуры ошибки, 64 hex>",
  "traceback": "Traceback (most recent call last): …"
}
```

| Поле | Обязательное | Правила |
|---|---|---|
| `app_version` | да | 1–64 символа |
| `os` | нет | 1–64 символа, по умолчанию `""` |
| `error_hash` | да | ровно 64 hex-символа `[0-9a-f]` |
| `traceback` | нет | текст; **санитайзится** (см. ниже), обрезается до 16 КБ |

**Санитайзер** (правило одно и тестируется): домашние каталоги
`C:\Users\<имя>\`, `/home/<имя>/` и `/Users/<имя>/` → `<пользователь>`; после
замены текст обрезается до 16 КБ (по кодовым точкам). Дополнительно сервер
**не логирует** тело отчёта и **не пишет** client IP в access-логи приложением.

**202**:

```json
{"id": "…-uuid", "received_at": "2026-11-02T10:00:00Z"}
```

Ошибки: 413, 415, 422.

**Ретеншн:** отчёты хранятся 30 дней, после чего удаляются
(политика документирована; фоновый очиститель — M8/M11).

## 6. Модель сценария и валидация

- Формат — IR `.acl.json` v1 (`{"version": 1, "name"?, "nodes": [...]}`),
  единый источник истины — `core/ir/` desktop-приложения.
- Сервис **не дублирует схему**: валидация через
  `core.ir.schema.scenario_from_mapping` (ADR №37). Ошибки схемы → 422 со
  списком `errors` из `ValidationIssue`.
- Неизвестные ключи в IR игнорируются (совместимость вперёд), неизвестный
  `type` узла — ошибка.
- В БД сохраняется **нормализованный** IR (`Scenario.to_mapping()` после
  валидации), поэтому скачивание всегда отдаёт канонический JSON.
- Состояние холста Blockly (`editor.workspace`) при публикации **не
  сохраняется** (тело приёма — только `scenario`); при открытии блочный
  редактор пересоберёт блоки из IR (совпадает с поведением M4, ADR №19/21).

### Лимиты валидации (из `core/ir/schema.py`)

| Параметр | Значение |
|---|---|
| Тело запроса | ≤ 1 048 576 байт (1 МБ), проверяется до чтения в память |
| Узлов в сценарии | ≤ 10 000 |
| Глубина вложенности | ≤ 32 |
| Ошибок в ответе 422 | ≤ 50 |
| Имя сценария (в IR) | ≤ 200 символов |
| Координаты | в диапазоне, заданном `core.settings` |
| `loop.times` | 1–1 000 000 или `null` |
| `delay.seconds` | 0.0–3600.0 |

## 7. Идемпотентность `POST /v1/scenarios`

Заголовок `Idempotency-Key`: 8–128 символов `[A-Za-z0-9._:-]`, смысл —
«этот клиентский запрос уже мог уйти повторно».

Семантика:

1. **Ключа нет** — обычное создание; возможны дубликаты (клиент сам
   обеспечивает уникальность).
2. **Ключ есть, сценария с ним нет** — создание; ключ привязывается к строке.
3. **Тот же ключ, то же тело** (совпадает канонический хэш тела, § «Тело» ниже)
   в течение **24 часов** — не создаётся дубль; ответ 201 с теми же данными
   и заголовком `Idempotent-Replay: true`.
4. **Тот же ключ, другое тело** в течение 24 часов — **409**.
5. **Ключ старше 24 часов** (`CLICKIT_IDEMPOTENCY_TTL_HOURS`) — резервация
   протухла: снять ключ со старой строки и создать новую в той же транзакции.

- «Тело» для сравнения — канонический JSON `{name, description, scenario}`
  с `json.dumps(sort_keys=True, ensure_ascii=False, separators=(",", ":"))` и
  sha256 от него в UTF-8.
- Гонка двух одновременных запросов с одним ключом резолвится через
  уникальный индекс: второй видит `IntegrityError`, перечитывает строку по
  ключу и возвращает replay (или 409 при расхождении тела) — без 500.
- TTL очищается и в фоне (M8/M11); поведение, гарантированное контрактом,
  — только пункты 3–5 выше.

## 8. Схема БД (PostgreSQL 16)

```sql
-- Сценарии
CREATE TABLE scenarios (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name                text NOT NULL CHECK (char_length(name) BETWEEN 1 AND 200),
    description         text NOT NULL DEFAULT '' CHECK (char_length(description) <= 2000),
    ir                  jsonb NOT NULL,               -- нормализованный IR
    sha256              char(64) NOT NULL,            -- канонический хэш IR, см. ниже
    idempotency_key     text,                          -- NULL = не зарезервирован
    idempotency_body    char(64),                      -- sha256 тела запроса (§7)
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX ux_scenarios_idempotency_key ON scenarios (idempotency_key);
CREATE INDEX ix_scenarios_sha256 ON scenarios (sha256);
CREATE INDEX ix_scenarios_created_at ON scenarios (created_at DESC);

-- Crash-отчёты
CREATE TABLE crash_reports (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    app_version text NOT NULL CHECK (char_length(app_version) BETWEEN 1 AND 64),
    os          text NOT NULL DEFAULT '' CHECK (char_length(os) <= 64),
    error_hash  char(64) NOT NULL,
    traceback   text,                                  -- санитайзер + ≤ 16 КБ
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_crash_reports_created_at ON crash_reports (created_at);
```

- `sha256` сценария — канонический JSON `Scenario.to_mapping()`
  (`json.dumps(sort_keys=True, ensure_ascii=False, separators=(",", ":"))`),
  sha256 в UTF-8, hex. Это же значение — в `ETag`.
- «Без PII»: в отчётах нет имён пользователей, путей и IP (см. §5.9);
  в `scenarios` контент — на совести автора (модерация — вне M7).

## 9. Конфигурация сервиса (env)

| Переменная | Обязательная | По умолчанию | Назначение |
|---|---|---|---|
| `CLICKIT_DB_URL` | да | — | SQLAlchemy URL, напр. `postgresql+psycopg://clikit:clikit@localhost:5432/clikit` |
| `CLICKIT_API_KEY` | да | — | ключ записи, ≥ 16 символов |
| `CLICKIT_ADMIN_API_KEY` | нет | — | ключ удаления; если задан — DELETE требует только его |
| `CLICKIT_MAX_BODY_BYTES` | нет | `1048576` | лимит тела запроса |
| `CLICKIT_IDEMPOTENCY_TTL_HOURS` | нет | `24` | срок резервации `Idempotency-Key` |
| `CLICKIT_GIT_SHA` | нет | `unknown` | sha сборки для `/version` |
| `CLICKIT_BUILD_TIME` | нет | `""` | время сборки для `/version` |
| `CLICKIT_LOG_LEVEL` | нет | `INFO` | уровень журнала сервиса |

Секреты — только в env/`.env`; в Git — `.env.example` без значений (ключи
маскируются при логировании и в ответах).

## 10. Клиент и CLI (контракт M7, T4.2)

### `cloud/client.py`

```python
class PublishedScenario:  # id, name, sha256, created_at, updated_at, url
class ScenarioPage:       # items: list[PublishedScenario], total, limit, offset
class CrashReceipt:       # id, received_at

class CloudClient:
    def __init__(self, base_url: str, *, api_key: str | None = None,
                 timeout: float = 5.0, attempts: int = 3,  # до 3 попыток:
                 backoff_base: float = 0.5, jitter: float = 0.25) -> None: ...
    def publish(self, document: dict, *, name: str | None = None,
                description: str | None = None,
                idempotency_key: str | None = None) -> PublishedScenario: ...
    def download(self, scenario_id: str) -> dict: ...           # полный .acl.json
    def list(self, *, limit: int = 20, offset: int = 0) -> ScenarioPage: ...
    def delete(self, scenario_id: str) -> None: ...
    def report_crash(self, *, app_version: str, os: str,
                     error_hash: str, traceback: str | None = None) -> CrashReceipt: ...
```

Ошибки — иерархия `CloudError`:

| Исключение | Откуда |
|---|---|
| `CloudError` (база: status, detail, request_id) | общее |
| `CloudAuthError` | 401/403 |
| `CloudNotFoundError` | 404 |
| `CloudValidationError(issues)` | 422 |
| `CloudConflictError` | 409 |
| `CloudTooLargeError` | 413 |
| `CloudServerError` | 5xx / сеть после исчерпания попыток |

Retry **только** на 5xx, таймауты и сетевые ошибки: до 3 попыток, паузы
`0.5, 1, 2` с ±25 % jitter. 4xx не ретраятся.

### `scripts/cloud_publish.py`

```
python scripts/cloud_publish.py publish <файл.acl.json> [--name ...] [--description ...]
                                              [--idempotency-key ...] [--url URL] [--api-key KEY]
python scripts/cloud_publish.py download <id> --output <файл.acl.json> [--url URL]
python scripts/cloud_publish.py list [--limit N] [--offset N]
python scripts/cloud_publish.py delete <id>
python scripts/cloud_publish.py crash-report <файл.json>
```

Параметры `--url`/`--api-key` можно заменить env `CLICKIT_CLOUD_URL`,
`CLICKIT_API_KEY`. Коды выхода: `0` ok, `2` ошибка использования,
`3` авторизация, `4` не найдено, `5` невалидные данные/сценарий,
`6` сеть/сервер.

## 11. Проверка контракта (примеры)

```bash
curl -s localhost:8000/readyz
curl -s localhost:8000/version
curl -s -X POST localhost:8000/v1/scenarios \
  -H "Content-Type: application/json" -H "X-API-Key: $CLICKIT_API_KEY" \
  -H "Idempotency-Key: demo-1" -d @scenario.json            # 201
curl -s -X POST localhost:8000/v1/scenarios \
  -H "Content-Type: application/json" -H "X-API-Key: $CLICKIT_API_KEY" \
  -H "Idempotency-Key: demo-1" -d @scenario.json            # 201 + Idempotent-Replay: true
curl -s localhost:8000/v1/scenarios/<id>                    # 200, ETag
curl -s "localhost:8000/v1/scenarios?limit=20&offset=0"     # 200
curl -s -X DELETE localhost:8000/v1/scenarios/<id> \
  -H "X-API-Key: $CLICKIT_API_KEY"                          # 204
```

## 12. Вне контракта M7 (сознательно)

- Аккаунты, OAuth, квоты, модерация, rate limit — вне M7.
- S3/CDN, версии сценариев, `PATCH`, поиск — вне M7.
- Метрики приложений, трейсы, алерты — M8; деплой — M9; безопасность/нагрузка — M11.