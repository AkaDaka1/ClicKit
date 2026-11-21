# Наблюдаемость ClicKit Cloud — локальный стек

> Практическое руководство по стеку наблюдаемости M8: как поднять Prometheus,
> Grafana, Loki, Promtail, Tempo и Alertmanager одной командой, что проверить и
> где искать логи, метрики и трейсы. Нормативный контракт HTTP API —
> [`docs/api.md`](api.md), цифры SLO — [`docs/sre/slo.md`](sre/slo.md).

## 1. Зачем стек

Сервис ClicKit Cloud сам отдаёт три вида телеметрии (M8 T1.1–T1.3):

| Сигнал | Куда пишет сервис | Кто собирает и хранит |
|---|---|---|
| Логи | JSON в stdout (ADR №61) | Promtail → Loki |
| Метрики | `GET /metrics` (ADR №62) | Prometheus, скрейп каждые 15 с |
| Трейсы | OTLP/HTTP `:4318` (ADR №63) | Tempo |

Стек добавляет к этому дашборды (T2.2), алерты (T3.1) и SLO-контур
(T3.2/T4.1). Без него метрики и трейсы сервиса некуда смотреть: `/metrics`
отдаёт текст, а не графики.

```
┌──────────────┐  /metrics 15s   ┌────────────┐
│ ClicKit API  │ ──────────────► │ Prometheus │ ──► Alertmanager ──► alert-sink
│ FastAPI      │  OTLP/HTTP      ├────────────┤        │
│ + PostgreSQL │ ──────────────► │   Tempo    │        ▼
└──────┬───────┘  JSON stdout    ├────────────┤   Grafana UI
       │                         │   Loki     │ ◄── Promtail (Docker API)
       └───────── stdout ───────►└────────────┘
```

## 2. Что понадобится

| Вариант | Требования |
|---|---|
| Рекомендуемый | Docker Desktop (Linux-контейнеры) с Compose v2.20+ — нужен `include:`. |
| Ресурсы | ~2 ГБ ОЗУ на стек; у сервисов заданы лимиты памяти/CPU. |
| Секреты | `.env` с `CLICKIT_API_KEY` и `POSTGRES_PASSWORD` (см. `docs/cloud.md` §3.1). |

Порты стека публикуются **только на localhost** (`127.0.0.1`). В интернет
стек не выставляется — TLS, домен и защита периметра — M9/M11.

## 3. Быстрый старт

Из корня репозитория:

```powershell
Copy-Item .env.example .env
# заполните CLICKIT_API_KEY (≥ 16 символов) и POSTGRES_PASSWORD
docker compose -f docker-compose.observability.yml up -d --build
docker compose -f docker-compose.observability.yml ps
```

`--build` нужен при первом запуске и после изменения кода сервиса: образ
`clikit-service:local` собирается из `docker/Dockerfile.service`.

Файл включает `docker-compose.cloud.yml`, поэтому поднимаются и API с
PostgreSQL: Prometheus должен видеть живой `/metrics`, а API — отправлять
спаны в Tempo по общей Docker-сети. Это одна команда, один проект
(`clikit-observability`), одна сеть.

### 3.1. Адреса

| Компонент | URL | Что смотреть |
|---|---|---|
| API | <http://127.0.0.1:8000> | `/healthz`, `/readyz`, `/metrics`, `/docs` |
| Prometheus | <http://127.0.0.1:9090> | `/targets`, `/graph`, `/rules` |
| Grafana | <http://127.0.0.1:3000> | дашборд `ClicKit Cloud — обзор`, источники данных, Explore |
| Alertmanager | <http://127.0.0.1:9093> | принятые алерты, silences (T3.1) |
| Loki | <http://127.0.0.1:3100> | `/ready`, `/metrics` (UI — в Grafana) |
| Tempo | <http://127.0.0.1:3200> | `/ready`, `/metrics` (UI — в Grafana) |
| alert-sink | <http://127.0.0.1:8080/alerts> | последние принятые вебхуки (JSON) |

Порты меняются в `.env`: `CLICKIT_PROMETHEUS_PORT`, `CLICKIT_GRAFANA_PORT`,
`CLICKIT_ALERTMANAGER_PORT`, `CLICKIT_LOKI_PORT`, `CLICKIT_TEMPO_PORT`,
`CLICKIT_OTLP_HTTP_PORT`, `CLICKIT_ALERT_SINK_PORT`.

## 4. Проверка: все targets UP

Главный чекпоинт T2.1 — Prometheus видит все цели, а UI открываются.

```powershell
# 1. Состояние контейнеров: api/db/prometheus/... — healthy
docker compose -f docker-compose.observability.yml ps

# 2. Все targets UP (health == "up" у каждого)
curl.exe -s http://127.0.0.1:9090/api/v1/targets |
  ConvertFrom-Json | ForEach-Object { $_.data.activeTargets } |
  Select-Object @{n='job';e={$_.labels.job}}, health
```

Ожидаемые `job`: `prometheus`, `clikit-api`, `alertmanager`, `loki`,
`promtail`, `tempo`, `grafana`, `node-exporter` — у всех `health = up`.
Итого 8 целей; `db` и `migrate` из cloud-compose целями не являются.

```powershell
# 3. UI и API отвечают 200
curl.exe -s -o NUL -w "%{http_code}`n" http://127.0.0.1:9090/-/ready      # 200
curl.exe -s -o NUL -w "%{http_code}`n" http://127.0.0.1:3000/api/health   # 200
curl.exe -s -o NUL -w "%{http_code}`n" http://127.0.0.1:9093/-/ready      # 200
curl.exe -s -o NUL -w "%{http_code}`n" http://127.0.0.1:3100/ready        # 200
curl.exe -s -o NUL -w "%{http_code}`n" http://127.0.0.1:3200/ready        # 200
curl.exe -s -o NUL -w "%{http_code}`n" http://127.0.0.1:8080/healthz      # 200
```

Grafana открывается без формы входа: включён анонимный просмотр с ролью
Viewer, а дашборды приходят из Git, а не создаются руками в UI (ADR №39).

Loki сразу после старта контейнера отвечает на `/ready` 503 — это штатный
прогрев ring/WAL, а не ошибка конфигурации. Проверяйте повторно в течение
1–2 минут; healthcheck у Loki намеренно нет (образ distroless).

### 4.1. Дашборд Grafana (чекпоинт T2.2)

Grafana поднимается с готовым дашбордом `ClicKit Cloud — обзор`
(UID `clikit-cloud`): он провизионируется как код из
`observability/grafana/dashboards/clikit-cloud.json`, правки из UI запрещены
(`allowUiUpdates: false`), поэтому «как на картинке» воспроизводится из Git.
Проверка после `up -d`:

```powershell
# 1. Дашборд в API (uid, 13 панелей)
Invoke-RestMethod http://127.0.0.1:3000/api/dashboards/uid/clikit-cloud |
  ForEach-Object { "$($_.dashboard.uid): $(@($_.dashboard.panels).Count) panels" }

# 2. Открыть в браузере
# http://127.0.0.1:3000/d/clikit-cloud
```

Панели: RPS и 5xx за 5 мин, доступность за 30 дней и остаток error budget,
burn rate за 1/6 ч, in-flight, RPS по маршрутам, p50/p95/p99 задержки,
пул БД, CPU/RAM Docker-хоста, состояние targets и логи API из Loki.
Скриншот дашборда — в `README.md`.

**Формулы SLO не копируются в JSON.** Панели читают записи
`clikit:http_requests:rate5m`, `clikit:http_errors:ratio_rate5m`,
`clikit:sli_availability:ratio_rate30d`, `clikit:slo_burn_rate:ratio_*` и
`clikit:slo_error_budget:consumed_ratio_30d` из recording rules (T0.1).
В T2.2 исправлена их обработка пустого трафика: когда счётчики уже
существуют, но `rate` равен нулю, `or vector(1)` в знаменателе не срабатывал,
и SLI становился `NaN`. Теперь знаменатель проходит через `> 0`, а значение
по умолчанию подставляется внешним `or vector(...)`; новый сценарий
`promtool test rules` проверяет именно этот случай.

## 5. Логи, метрики, трейсы: сквозная проверка

Сгенерируйте трафик (нужен `httpx`, см. `docs/cloud.md` §3.4):

```powershell
$env:CLICKIT_CLOUD_URL = "http://127.0.0.1:8000"
$env:CLICKIT_API_KEY = "<ключ из .env>"
python scripts/cloud_publish.py publish resources/examples/click_pause_loop.acl.json
```

### 5.1. Логи (Promtail → Loki)

```powershell
curl.exe -s "http://127.0.0.1:3100/loki/api/v1/query_range?query=%7Bservice%3D%22api%22%7D&limit=5" |
  ConvertFrom-Json | ForEach-Object { $_.data.result } |
  Select-Object -ExpandProperty values -First 5
```

В Grafana → Explore → Loki тот же поток ищется запросом
`{service="api"}`; JSON-поля доступны через `| json`
(`level`, `request_id`, `trace_id`, `path`, `status`).

Метки потока — только низкой кардинальности: `container`, `service`,
`stream`, `level`. `request_id` и `trace_id` остаются в строке и в
structured metadata: превращать их в метки нельзя — поток на каждый запрос
взорвёт индекс Loki.

### 5.2. Метрики (Prometheus)

```powershell
# RPS по пользовательским маршрутам (recording rule из T0.1)
curl.exe -s "http://127.0.0.1:9090/api/v1/query?query=clikit:http_requests:rate5m" |
  ConvertFrom-Json | ForEach-Object { $_.data.result }
```

Если запрос только что опубликован, для `rate` нужно два скрейпа — подождите
15–30 секунд. Существеннее окно `rate` (5 минут): при единичных запросах
запись `clikit:http_requests:rate5m` честно показывает `0`. Для наглядной
проверки возьмите сырой счётчик — он растёт с каждым запросом:

```powershell
curl.exe -s "http://127.0.0.1:9090/api/v1/query?query=clikit_http_requests_total" |
  ConvertFrom-Json | ForEach-Object { $_.data.result } |
  Select-Object @{n='route';e={$_.metric.route}}, @{n='status';e={$_.metric.status}},
                @{n='count';e={$_.value[1]}}
```

Метрики API видны на `/targets` → `clikit-api`, а значения — в `/graph`.

### 5.3. Трейсы (Tempo)

1. Возьмите `trace_id` из строки журнала (§5.1) или `request_id` из заголовка
   ответа API.
2. Grafana → Explore → Tempo → поиск по `trace_id`.
3. В трейсе — HTTP-спан (`GET /v1/scenarios/{scenario_id}`) и дочерние спаны
   SQL; `trace_id` совпадает с JSON-журналом (ADR №41, №63).

Текст SQL в спаны не пишется — это данные сценария.

### 5.4. Алерты (T3.1)

Правила — `observability/prometheus/alerts.yml`, маршрутизация и подавление —
`observability/alertmanager/alertmanager.yml`. Все алерты читают recording rules
из T0.1, поэтому формулы не дублируются, а пороги описаны в
`docs/sre/slo.md` §11.

```powershell
# 1. Правила загружены Prometheus (12 записей + 7 алертов)
curl.exe -s http://127.0.0.1:9090/api/v1/rules |
  ConvertFrom-Json | ForEach-Object { $_.data.groups } |
  Select-Object name, @{n='rules';e={$_.rules.Count}}

# 2. Активные алерты (в норме — пусто)
Invoke-RestMethod "http://127.0.0.1:9090/api/v1/alerts" |
  Select-Object -ExpandProperty data | Select-Object -ExpandProperty alerts

# 3. Alertmanager видит алерты
Invoke-RestMethod "http://127.0.0.1:9093/api/v2/alerts"
```

Чекпоинт «сломай и почини»: остановите API и подождите ~1.5 минуты —
`ClikitApiDown` перейдёт в `firing` (видно в `/api/v1/alerts`, в UI
Alertmanager и в `GET /alerts` приёмника), верните API — тот же алерт
перейдёт в `resolved` (`send_resolved: true`).

```powershell
docker compose -f docker-compose.observability.yml stop api   # → firing (~1 мин)
docker compose -f docker-compose.observability.yml start api  # → resolved
Invoke-RestMethod http://127.0.0.1:8080/alerts | ConvertTo-Json -Depth 5
```

Проверка самих правил без контейнера стека:

```powershell
docker run --rm --entrypoint promtool -v "${PWD}/observability:/observability:ro" `
  prom/prometheus:v3.16.0 check rules /observability/prometheus/recording_rules.yml `
                                        /observability/prometheus/alerts.yml
docker run --rm --entrypoint promtool -v "${PWD}/observability:/observability:ro" `
  prom/prometheus:v3.16.0 test rules /observability/prometheus/tests/alerts_test.yml
```

Пороги: `High5xxRate` — 5xx > 1 % за 5 мин; `HighScenarioLatency` — p95 >
300 мс за 10 мин; `ClikitApiDown` — target down 1 мин; `FastErrorBudgetBurn` /
`SlowErrorBudgetBurn` — burn rate 14.4 (1 ч) / 6 (6 ч); `DbPoolExhausted` —
`in_use >= 5`; `HostMemoryLow` — свободно < 10 % памяти Docker-хоста.
`ClikitApiDown` подавляет следствия (5xx, латентность, пул).

## 6. Остановка, данные и ограничения

```powershell
# Остановить, сохранив данные в volumes
docker compose -f docker-compose.observability.yml down

# Удалить и контейнеры, и данные (необратимо)
docker compose -f docker-compose.observability.yml down -v
```

- **Не поднимайте одновременно** `docker-compose.cloud.yml` и этот файл:
  проекты разные, а порт API 8000 один. Для стека наблюдаемости этот файл —
  единственная команда запуска.
- Когда стек поднят, команды `docker compose` **без `-f`** относятся к
  `docker-compose.yml` (тестовая среда desktop), а не к стеку наблюдаемости:
  для `stop db`/`start db` в §7 указывайте файл явно.
- Данные: `prometheus-data`, `grafana-data`, `loki-data`, `promtail-data`,
  `tempo-data`, `alertmanager-data` и `pgdata` из cloud-compose.
- Retention: Prometheus — 40 дней (ADR №60), Loki — 30 дней, Tempo — 14 дней.
- Лимиты контейнеров (мера риска «стек съест память»): Prometheus/Grafana/
  Loki/Tempo — 512 МБ, Promtail — 256 МБ, Alertmanager/alert-sink — 128 МБ.
- Promtail в LTS и EOL в 2026 (Grafana переводит агентов на Alloy). План M8 §3
  фиксирует Promtail; миграция на Alloy — отдельное решение после вехи.
- `GF_AUTH_ANONYMOUS_ORG_ROLE=Viewer` и порты на localhost: стек не
  предназначен для публикации в интернет.

## 7. Диагностика

| Симптом | Причина и решение |
|---|---|
| `target clikit-api` — DOWN | API не запущен или unhealthy: `ps`, `logs api`. `migrate` должен завершиться с кодом 0. |
| `target promtail` — DOWN | Promtail не стартовал: `logs promtail`; проверьте права на `/var/run/docker.sock`. |
| В Loki нет логов | Promtail не видит контейнер API: `logs promtail`, фильтр `com.docker.compose.project=clikit-observability`. |
| В Tempo нет трейсов | У API не задан `CLICKIT_OTEL_ENDPOINT`: он появляется только в этом compose-файле (`http://tempo:4318`). |
| Grafana показывает «No data sources» | Provisioning не смонтирован: `logs grafana`, каталог `observability/grafana/provisioning`. |
| Loki `/ready` отвечает 503 после старта | Штатный прогрев ring/WAL: повторите запрос через 1–2 минуты. Если 503 держится дольше — `logs loki` (том `loki-data`, права на `/loki`). |
| `network ... not found` при `include` | Compose < 2.20: обновите Docker Desktop/Compose. |
| `port is already allocated` | Порт занят: поменяйте `CLICKIT_*_PORT` в `.env`. |
| `CLICKIT_..._PORT` не подействовал | `.env` читается из каталога запуска: выполняйте команду из корня репозитория. |
| Пусто в `/alerts` после алерта | Проверьте `/api/v1/alerts` Prometheus: если алерта нет, не сработало правило (`promtool check rules`). Если есть, но приёмник пуст — `logs alertmanager` и `logs alert-sink`. |
| `ClikitApiDown` не проходит в resolved | Prometheus должен снова скрейпить `up=1`; проверьте `/api/v1/targets` и `group_interval` в Alertmanager (critical — 30 с). |

## 8. Связанные документы

- [`docs/api.md`](api.md) — контракт API, `GET /metrics`, конфигурация env.
- [`docs/cloud.md`](cloud.md) — запуск и эксплуатация сервиса без стека.
- [`docs/sre/slo.md`](sre/slo.md) — SLI/SLO, error budget, retention 40 дней.
- [`docs/sre/runbook.md`](sre/runbook.md) — что делать по каждому алерту
  (T3.2): 8 сценариев с командами и критериями восстановления.
- [`docs/sre/postmortem-template.md`](sre/postmortem-template.md) — шаблон
  blameless-разбора; реальный пример —
  [`docs/sre/postmortems/2026-10-29-release-pipeline.md`](sre/postmortems/2026-10-29-release-pipeline.md).
- [`plans/M8-observability.md`](../plans/M8-observability.md) — план вехи и
  журнал задач.
