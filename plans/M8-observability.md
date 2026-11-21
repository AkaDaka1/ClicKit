# M8 — Наблюдаемость и SLO

> План создан 2026-11-01. Статус: ✅ выполнен (T0.1 ✅, T1.1 ✅, T1.2 ✅ — 2026-11-13, T1.3 ✅ — 2026-11-16, T2.1 ✅, T2.2 ✅ — 2026-11-16, T3.1 ✅ — 2026-11-16, T3.2 ✅ — 2026-11-21, T4.1 ✅ — 2026-11-21, T5.1 ✅ — 2026-11-21).
> Зависимость: M7 (работающий сервис и БД). Без сервиса метрикам нечего
> измерять; M8 не добавляет новые продуктовые функции.

## 1. Цель

Сделать ClicKit Cloud наблюдаемым и управляемым по надёжности: понять, что
происходит с сервисом в любой момент, увидеть деградацию до жалоб
пользователей и иметь измеримый ответ на вопрос «мы выполняем обещания?».

Результат вехи — не «галочки про Prometheus», а полный контур:
**лог → метрика → алерт → runbook → SLO → постмортем**.

## 2. Критерий готовности

- [x] В логах JSON с `request_id` и `trace_id`; секреты и API-ключи не пишутся.
- [x] `GET /metrics` отдаёт `clikit_http_requests_total`,
      `clikit_http_request_duration_seconds` (гистограмма),
      `clikit_http_requests_in_flight`, `clikit_db_pool_connections`,
      `clikit_build_info`.
- [x] Трейс запроса виден в Tempo: спаны HTTP и запроса к БД; `trace_id`
      из трейса совпадает с логом.
- [x] `docker compose -f docker-compose.observability.yml up -d` поднимает
      Prometheus, Grafana, Loki, Promtail, Tempo, Alertmanager.
- [x] Дашборд Grafana хранится JSON-файлом в репозитории: RPS, error rate,
      p50/p95/p99, in-flight, БД, CPU/RAM; скриншот — в README.
- [x] Алерты: 5xx > 1% за 5 мин, p95 > 300 мс за 10 мин, target down 1 мин,
      быстрый/медленный burn rate error budget, пул БД, память.
- [x] `stop api` → алерт переходит в firing и виден в Alertmanager/приёмнике;
      возврат сервиса → resolved.
- [x] `docs/sre/slo.md`: SLI, SLO 99.5%, error budget, окно 30 дней,
      политика исчерпания бюджета; `docs/sre/runbook.md` — минимум 5 сценариев.
- [x] Реальный постмортем по инциденту релиза 2026-10-29 и шаблон постмортема.
- [x] `promtool check rules` и `promtool test rules` зелёные; JSON-логи
      проверяются тестом схемы.

## 3. Согласованные параметры

| Параметр | Решение |
|---|---|
| SLO доступности | 99.5% за 30 дней; error budget 0.5% ≈ 3 ч 36 мин |
| SLO latency | p95 ≤ 300 мс для успешных `GET /v1/scenarios/{id}` и `POST /v1/scenarios` |
| SLI | доля успешных ответов (2xx/3xx) от всех, кроме 4xx клиента; latency по 2xx/3xx |
| Окно | 30 дней, rolling; быстрый burn rate — 1 ч, медленный — 6 ч |
| Скрап | Prometheus каждые 15 с, retention **40 дней** локально (30-дневное окно SLO + 10 дней запаса; уточнено 2026-11-13 в T0.1, исходно было 15 дней) |
| Логи | JSON в stdout; в контейнере — stdout/stderr, сбор — Promtail → Loki |
| Трейсы | OpenTelemetry SDK → OTLP HTTP → Tempo; sampling 100% локально |
| Дашборды | Provisioning as code; JSON в `observability/grafana/dashboards/` |
| Алерты | Prometheus rules + Alertmanager; приёмник локально — webhook-sink |
| Секреты | Не в правилах и не в логах; datasource-пароли — env |

## 4. Модули и интерфейсы

### 4.1. Сервис

- `service/app/observability/logging.py` — JSON-форматтер, `request_id`,
  `trace_id`, уровень, длительность, статус; исключения без секретов.
- `service/app/observability/metrics.py` — счётчики/гистограммы, `/metrics`.

  Реализовано в T1.2: `ServiceMetrics` (приватный `CollectorRegistry`),
  `HttpMetricsMiddleware` (счётчик, гистограмма, in-flight; запись ровно один
  раз), `render_metrics` (текст Prometheus 1.0 + `clikit_db_pool_connections`
  и `clikit_build_info` на момент скрейпа). Метки — `method`, `route`
  (шаблон FastAPI), `status`; несовпавшие пути — `route="unmatched"`.
  `Database.pool_samples()` отдаёт состояния пула SQLAlchemy.
- `service/app/observability/tracing.py` — OTel, FastAPI/SQLAlchemy
  instrumentation, OTLP-экспортёр.

  Реализовано в T1.3: `Tracing` создаёт `TracerProvider` на приложение
  (свой реестр спанов, как `CollectorRegistry` в T1.2), HTTP-спан —
  `FastAPIInstrumentor` с шаблоном маршрута в имени, спан БД — собственный
  `SqlTracingListener` на событиях SQLAlchemy (`before/after_cursor_execute`):
  официальная `opentelemetry-instrumentation-sqlalchemy` требует
  `sqlalchemy < 2.1`. Текст SQL в атрибуты не пишется. `trace_id` в журнал
  кладёт `TraceContextMiddleware` внутри HTTP-спана; экспорт — батчевый
  OTLP/HTTP в Tempo (`/v1/traces`), настройки — `CLICKIT_OTEL_*`.
- middleware: `X-Request-ID` (входящий или новый), запись в лог и ответ.

  Реализовано в T1.1: `service/app/observability/logging.py` (`JsonFormatter`,
  `CorrelationFilter`, `configure_logging`), контекст — `ContextVar`
  `current_request_id`/`current_trace_id`, access-запись — в
  `service/app/request_id.py` (`extra`: `event`, `method`, `path`, `status`,
  `duration_ms`).

### 4.2. Инфраструктура наблюдаемости

```
observability/
├── prometheus/
│   ├── prometheus.yml
│   ├── alerts.yml       # T3.1: 7 алертов (availability/latency/resources)
│   │                    # + T4.1: ErrorBudgetFreeze/ErrorBudgetExhausted
│   ├── tests/           # T0.1/T3.1: slo_rules_test.yml, alerts_test.yml
│   └── recording_rules.yml
├── alertmanager/alertmanager.yml  # T3.1: маршрутизация по severity + inhibition
├── grafana/
│   ├── provisioning/datasources/datasources.yml
│   ├── provisioning/dashboards/dashboards.yml
│   └── dashboards/      # T2.2: clikit-cloud.json (дашборд «ClicKit Cloud — обзор»)
├── loki/loki-config.yml
├── promtail/promtail-config.yml
└── tempo/tempo.yml
docker-compose.observability.yml
docs/observability.md    # запуск и проверка стека (T2.1)
docs/observability-demo.md  # T5.1: демо «сломай и почини» на 5 минут
scripts/alert_sink.py    # локальный приёмник вебхуков Alertmanager
scripts/slo_report.py    # T4.1: расчёт error budget и режим политики в терминале
scripts/observability_demo.py  # T5.1: исполняемое демо (check/run, коды 0/1/2)
```

### 4.3. Документы

- `docs/sre/slo.md` — SLI/SLO, окно, error budget, burn rate, политика;
  §2 закрывает и вопрос «чем SLA отличается от SLO» (отдельный `sla.md` не
  заводится, чтобы не появился второй источник цифр — ADR №40).
- `docs/sre/runbook.md` — сервис недоступен, высокий 5xx, latency, БД, память,
  диск, пайплайн релиза (8 сценариев).
- `docs/sre/postmortem-template.md` — blameless-шаблон.
- `docs/sre/postmortems/2026-10-29-release-pipeline.md` — реальный разбор
  трёх упавших прогонов `Release` и фикса путей `NOTICE.txt`/артефактов.
- `docs/observability-demo.md` — T5.1: демо «сломай и почини» (5 минут,
  ручной сценарий + автоматический прогон), включая раздел «Чего демо не
  показывает» (слепое пятно SLI при полном падении — ADR №69).

## 5. Решения (ADR; итог — в `AI_CONTEXT.md` §3.3)

- **ADR №39 — стандартный стек наблюдаемости.** Prometheus + Grafana + Loki +
  Tempo + Alertmanager: минимальный набор, покрывающий метрики, логи, трейсы
  и алерты, без ELK/Kafka/Istio. Дашборды и правила — в Git.
- **ADR №40 — SLO как контракт с самим собой.** SLO 99.5% и error budget
  фиксируются до оптимизаций; измерения — по фактическому трафику, а не
  «на глаз». Исчерпание бюджета останавливает рискованные изменения.
- **ADR №41 — корреляция через request_id/trace_id.** Один идентификатор
  проходит HTTP → лог → трейс; без него разбор инцидента снова ручной.
- **ADR №60 — границы SLI и retention 40 дней** (2026-11-13, T0.1): в SLI
  входят только маршруты `/v1/...` (`route` — шаблон FastAPI, не сырой путь);
  4xx клиента не жгут error budget; пустой трафик считается выполнением SLO.
  Окно SLO — 30 дней, поэтому retention Prometheus поднят с 15 до 40 дней
  (окно + 10 дней запаса): 30-дневный SLI нельзя посчитать из 15 дней данных.
  Уточнено в T2.2: при уже существующих счётчиках с нулевым `rate` знаменатель
  SLI отсекается через `> 0` — иначе `or vector(1)` не срабатывал и панели
  дашборда показывали `NaN`; поведение зафиксировано promtool-сценарием.
- **ADR №65 — дашборд как код, а не как состояние UI** (2026-11-16, T2.2):
  `observability/grafana/dashboards/clikit-cloud.json` — единственный источник
  дашборда; provisioning read-only, `editable: false`. Панели SLO читают
  recording rules T0.1, а не копируют формулы: иначе правка порога в
  `docs/sre/slo.md` и дашборде разъехалась бы. Метрики в панелях — только
  низкой кардинальности (`route` — шаблон FastAPI); статический тест
  `tests/service/test_grafana_dashboard.py` не даёт в JSON ни id сценариев,
  ни секретов, ни неизвестных метрик.
- **ADR №66 — алерты читают recording rules; promtool в CI** (2026-11-16,
  T3.1): `observability/prometheus/alerts.yml` не дублирует формулы SLI, а
  ссылается на записи T0.1 (`clikit:slo_burn_rate:*`,
  `clikit:http_errors:ratio_rate5m`), поэтому порог SLO живёт в одном месте
  (`docs/sre/slo.md`). Единственная новая запись — `clikit:sli_latency:p95_rate5m`
  (та же формула, что в ad-hoc-запросе §8, вынесена в правило, чтобы алерт
  `HighScenarioLatency` не копировал `histogram_quantile`). У каждого алерта
  обязательны `severity` (`critical`/`warning`) и окно `for`; `ClikitApiDown`
  подавляет следствия (5xx, латентность, пул) через Alertmanager inhibition.
  Правила — код: их синтаксис и семантику (`promtool check/test rules`) гоняет
  новый CI-job `observability-rules` на образе `prom/prometheus:v3.16.0` —
  той же версии, что стек; статический тест `tests/service/test_alerts.py`
  ловит расхождение порогов с документом SLO.
- **ADR №67 — runbook привязан к именам алертов, постмортем — к фактам CI**
  (2026-11-21, T3.2): `docs/sre/runbook.md` — не пересказ SLO, а процедура:
  у каждого алерта есть сценарий с «первыми 3 минутами», командами и
  критерием восстановления; пороги не дублируются, а ссылаются на `slo.md`.
  Связь проверяется тестом `tests/service/test_runbook.py`, поэтому
  переименование алерта без правки инструкции ломает сборку. Постмортем —
  blameless-шаблон с обязательными «действие → владелец → срок»; действия,
  которые не сделаны, остаются `⬜ открыто` (выдавать их за выполненные
  нельзя). Реальный разбор `2026-10-29-release-pipeline` опирается на номера
  прогонов GitHub Actions, коммиты и машинные строки ошибок, а не на память.

- **ADR №68 — error budget как вычисляемая величина, а не таблица**
  (2026-11-21, T4.1): режимы политики §7 (`normal`/`careful`/`freeze`/
  `exhausted`) считаются recording rules (`remaining_ratio_30d`,
  `remaining_minutes_30d`, `policy_state_30d`), алерты
  `ErrorBudgetFreeze`/`ErrorBudgetExhausted` читают `consumed_ratio_30d`,
  а `scripts/slo_report.py` воспроизводит тот же расчёт в терминале с кодом
  выхода 0/1/2/3 (задел для гейта деплоя M10). Пороги 50/75/100 % и бюджет
  216 мин заданы в одном месте — `docs/sre/slo.md`; копия формулы в дашборде,
  алерте, скрипте или runbook расценивается как дефект. Алерты политики
  не подавляются `ClikitApiDown` (простой API сам жжёт бюджет), а «нет
  данных» — код 3, а не 0: отсутствие измерения не равно выполнению SLO.

- **ADR №69 — демо проверяется состоянием, а не картинкой, и честно про
  слепое пятно SLI** (2026-11-21, T5.1): «сломай и почини» — это
  `scripts/observability_demo.py`, который опрашивает `/api/v1/alerts`,
  `/api/v2/alerts` и `/alerts` приёмника до фактического `firing`/`resolved`,
  а не спит фиксированные 90 секунд: правка `for` в правилах или частоты
  скрейпа не делает демо «зелёным по расписанию». Код выхода 0/1/2 пригоден
  для будущего гейта M10/M11; аварийное восстановление API выполняется в
  `finally`, потому что оставлять сервис выключенным нельзя (runbook §1.2).
  Документ `docs/observability-demo.md`
  содержит раздел «Чего демо не показывает»: падение API **не видно в SLI**
  (`slo.md` §3), бюджет при простое не жжётся, 5xx и латентность не
  генерируются — вместо видимости полного покрытия демо показывает границы
  контура. Сценарий и автоматика ссылаются на runbook §3, а не пересказывают
  пороги: единственный источник цифр — `slo.md`.

## 6. Граф задач

| ID | Задача | Зависимости | Чекпоинт (done = …) | Статус |
|---|---|---|---|---|
| T0.1 | SLI/SLO и PromQL-запросы, политика error budget | M7 | `docs/sre/slo.md` с формулами и цифрами; запросы проверены | ✅ |
| T1.1 | JSON-логи и `request_id` middleware | T0.1 | Логи парсятся, поля обязательны, секретов нет | ✅ |
| T1.2 | Prometheus-метрики и `/metrics` | T1.1 | Метрики scrapes, unit-тесты, имена стабильны | ✅ |
| T1.3 | OTel-трейсы и Tempo | T1.2 | Спан HTTP + БД, `trace_id` в логе | ✅ |
| T2.1 | Compose-стек наблюдаемости | T1.3 | Все targets UP, UI открываются | ✅ |
| T2.2 | Дашборд Grafana как код | T2.1 | JSON в Git, панели показывают трафик, скриншот | ✅ |
| T3.1 | Алерты и Alertmanager + приёмник | T2.2 | `stop api` → firing → resolved; `promtool test rules` | ✅ |
| T3.2 | Runbook и постмортем | T3.1 | 5 сценариев + реальный постмортем | ✅ |
| T4.1 | SLO/error budget и burn rate | T3.2 | Политика, алерты, расчёт на 30 дней | ✅ |
| T5.1 | Демо «сломай и почини» + README | T4.1 | 5-минутный сценарий воспроизводим с чистой машины | ✅ |

### Волны

```
Волна 1: T0.1
Волна 2: T1.1 → T1.2 → T1.3
Волна 3: T2.1 → T2.2
Волна 4: T3.1 → T3.2
Волна 5: T4.1 → T5.1
```

## 7. Список коммитов

1. `docs: SLI/SLO, PromQL-запросы и recording rules` (T0.1)
2. `feat: JSON-логи и request_id` (T1.1)
3. `feat: метрики Prometheus в сервисе` (T1.2)
4. `feat: трейсы OpenTelemetry` (T1.3)
5. `feat: compose-стек наблюдаемости` (T2.1)
6. `feat: дашборд Grafana как код` (T2.2)
7. `feat: алерты и Alertmanager` (T3.1)
8. `docs: runbook и постмортем` (T3.2)
9. `feat: error budget и политика SLO` (T4.1)
10. `feat: демо наблюдаемости сломай и почини` (T5.1) — `docs/observability-demo.md`,
    `scripts/observability_demo.py`, тесты и ссылки из README/runbook.

## 8. Чек-лист приёмки

- [x] Инцидент «сервис упал» разбирается по логам, метрикам и трейсу без
      чтения исходников.
- [x] Алерт срабатывает до того, как пользователь массово видит ошибки.
- [x] В SLO-документе есть цифры, окно, бюджет и правило действий.
- [x] Дашборд и правила восстанавливаются из Git, а не «руками в UI».
- [x] Постмортем blameless: факты, таймлайн, причины, действия, владельцы.
- [x] M7-функциональность не сломана; тесты сервиса зелёные.

## 9. Риски и меры

| Риск | Мера |
|---|---|
| Стек наблюдаемости «съест» память ноутбука | Лимиты контейнеров, retention 40 дней (≈2000 серий × 15 с), профиль `observability` в compose |
| Кардинальность меток взорвётся | Метки только `method`, `route`, `status`; без id и query-параметров |
| Логи с PII/секретами | Явный allowlist полей, тест схемы, gitleaks в M11 |
| Алерты шумят | `for`, severity, burn rate; тесты правил; подавление дублей |
| SLO выдуман | Сначала измерить трафик, затем зафиксировать; пересмотр раз в квартал |

## 10. Журнал задач

| Дата | Задача | Результат | Commit |
|---|---|---|---|
| 2026-11-01 | — | План создан; SLO и стек согласованы | — |
| 2026-11-13 | T0.1 | SLI/SLO зафиксированы: `docs/sre/slo.md` (99.5 % / 30 дней, бюджет 0.5 % = 216 мин, p95 ≤ 300 мс, burn rate 14.4/6, политика 50/75/100 %, границы SLI и ограничения), `observability/prometheus/recording_rules.yml` (11 записей), `observability/prometheus/tests/slo_rules_test.yml` (4 сценария promtool); retention Prometheus 15 → 40 дней — иначе 30-дневный SLO не посчитать (ADR №60, §3 обновлён); проверено `promtool check rules` (11 rules) и `promtool test rules` (SUCCESS) в `prom/prometheus:latest`; 8 статических тестов `tests/service/test_slo_docs.py`, полный прогон 515 passed | `58c34b7` |
| 2026-11-13 | T1.1 | JSON-журнал и корреляция: `service/app/observability/logging.py` — `JsonFormatter` (обязательные поля `timestamp`, `level`, `logger`, `message`, `service`, `version`, `request_id`, `trace_id`; необязательные `event`/`method`/`path`/`route`/`status`/`duration_ms`/`error_type`), `CorrelationFilter` из `ContextVar` (`current_request_id`, `current_trace_id` для T1.3), `configure_logging(level, secrets=…)` переводит uvicorn-логгеры на общий обработчик, `_LateBoundStreamHandler` берёт поток при каждой записи (иначе записи терялись после подмены stdout); маскировка секретов (значения ключей → `***`, пары `X-API-Key: …`/`password=…`) и санитайзер PII в traceback; доступ-запись `RequestContextMiddleware` — структурированные поля вместо текстовой строки, `main.py` передаёт ключи в `configure_logging`. `docs/cloud.md` §8.1 — формат и поиск по журналу; ADR №61. Тесты: 10 новых (`tests/service/test_json_logging.py`: схема полей, контекст, маскировка, traceback, сквозной access-лог, отсутствие ключа), обновлены `test_request_id.py`/`test_auth.py` (поля записи вместо текста); service — 251 passed, `ruff check`/`format --check` чисто | `5f9f8cd` |
| 2026-11-13 | T1.2 | Метрики Prometheus и `/metrics`: `service/app/observability/metrics.py` — `ServiceMetrics` (приватный `CollectorRegistry` на приложение, чтобы тестовые экземпляры не падали на `Duplicated timeseries`), `HttpMetricsMiddleware` (счётчик `clikit_http_requests_total`, гистограмма `clikit_http_request_duration_seconds` с корзиной `le="0.3"` — порогом SLO, gauge `clikit_http_requests_in_flight`; запись ровно один раз, в `http.response.start` и в `finally`), `render_metrics` (Prometheus 1.0 + `clikit_db_pool_connections` и `clikit_build_info` на момент скрейпа); `Database.pool_samples()` — состояния пула SQLAlchemy. Метки только `method`/`route`/`status`, `route` — шаблон FastAPI (`/v1/scenarios/{scenario_id}`), несовпавшие пути и 413 лимита тела — `unmatched`; 500 (ответ `ServerErrorMiddleware`) берёт маршрут из `scope` в `finally`, иначе 5xx выпадали бы из SLI. Скрейп `/metrics` не пишет access-запись и не считается в `in_flight`. Попутно: `unhandled_exception_handler` передаёт `request_id` в журнал явно (обработчик стоит выше `RequestContextMiddleware`), `CorrelationFilter` уважает явное поле. `docs/api.md` §5.4 и `docs/cloud.md` §8.1.1 обновлены; `prometheus-client>=0.20` в `requirements-service.txt`; ADR №62. Тесты: 18 новых (`tests/service/test_metrics.py`: форма серий, кардинальность, корзины, сквозной учёт 200/401/404/422/413/500, in-flight, подавление журнала, формат и пул БД) + 1 в `test_json_logging.py`; service — 271 passed, покрытие 96.44 %; полный прогон **545 passed**; проверено вживую `uvicorn` (`/healthz`, `/version`, `/metrics`, 404, 500; `route`-шаблоны, `in_flight 0`, `build_info`); `ruff check`/`format --check` чисто | `18e756c` |
| 2026-11-16 | T1.3 | OTel-трейсы и Tempo: `service/app/observability/tracing.py` — `Tracing` (создаёт `TracerProvider` на приложение через `install_tracer_provider`, HTTP-спан `FastAPIInstrumentor`, спан БД — самописный `SqlTracingListener` на `before/after_cursor_execute`, потому что официальная instrumentation-sqlalchemy требует `sqlalchemy<2.1`; текст SQL не пишется), `TraceContextMiddleware` — `trace_id` в журнал (внутри HTTP-спана), `active_trace_id`, `otlp_traces_url`; настройки `CLICKIT_OTEL_*` в `config.py` (enabled/endpoint/sample_rate/service_name) + `_env_bool`/`_env_float`; `main.py` — флаг `enable_tracing` (при явных `Settings` трейсинг выключен, иначе тесты висели на OTLP-таймауте), старт/остановка в `lifespan` через `run_in_threadpool`. Попутно исправлен порядок middleware: в списке `middleware=[...]` первым идёт внешний слой (зеркально `add_middleware`) — из-за перевёрнутого порядка 413 обходил request_id и метрики. ADR №63; `docs/api.md` §9, `docs/cloud.md` §8.1.2; `requirements-service.txt`; 23 теста `tests/service/test_tracing.py`; service — 294 passed (~18 с), полный прогон 568 passed; сквозная проверка вживую: HTTP-спан + `sqlite INSERT` в одном трейсе, `trace_id` в логе совпадает с трейсом, `clikit.request_id` равен `X-Request-ID` | см. `git log --grep T1.3` |
| 2026-11-16 | T2.1 | Compose-стек наблюдаемости: `docker-compose.observability.yml` (project `clikit-observability`, `include: docker-compose.cloud.yml` — общая Docker-сеть, pinned-образы, порты только `127.0.0.1`, volumes и лимиты CPU/RAM) поднимает `prometheus` (v3.16.0, scrape 15s, retention 40d, `--web.enable-lifecycle`, recording rules из T0.1, Alertmanager как приёмник), `grafana` (13.2.6, provisioning Prometheus/Loki/Tempo как код, анонимный Viewer), `loki` (3.6.11, retention `720h`, structured metadata), `promtail` (3.6.11, Docker API, фильтры `com.docker.compose.project=clikit-observability` + `com.docker.compose.service=api`; `request_id`/`trace_id` — не метки), `tempo` (3.1.1, OTLP/HTTP `:4318`), `alertmanager` (0.35.0 → локальный приёмник `alert-sink`) и `node-exporter` (`docker-host`). Конфиги: `observability/{prometheus,alertmanager,grafana,loki,promtail,tempo}/…`. `scripts/alert_sink.py` (stdlib HTTP-сервер: `POST /webhook`, `GET /alerts`, `GET /healthz`; журнал только `status`/`alertname`/`severity`/`summary` — остальные поля не утекают, ADR №41/№64; `_drain_body` для корректного 413 без RST на Windows). Документация: `docs/observability.md` (запуск, §4 чекпоинт targets/UI, §5 логи/метрики/трейсы/алерты, §7 диагностика), `docs/cloud.md` §8.1.3, `.env.example` — `CLICKIT_*_PORT`. Тесты: 8 в `tests/service/test_alert_sink.py` (включая 413/JSON/историю) + 18 в `tests/service/test_observability_stack.py` (include, pinned-образы, retention, OTLP/HTTP Tempo, localhost-порты, scrape-таргеты, правила→Alertmanager, 3 datasource, read-only провайдер дашбордов, политика меток Loki/Promtail, отсутствие секретов в YAML). Пройден живой чекпоинт `down`→`up -d --build`/`up -d --wait`: контейнеры healthy, **8/8 targets UP** (prometheus, clikit-api, alertmanager, loki, promtail, tempo, grafana, node-exporter), UI/API 200, Grafana отдаёт datasource prometheus/loki/tempo, HTTP-спан+SQL в одном трейсе Tempo (`da31ae9f…`), JSON-логи `{service="api"}` в Loki, ручной вебхук → `{"received":1}`; данные переживают `down`/`up` (сценарий `500486a7…`, логи, трейс). Полный прогон **595 passed**, service — 321 (94.22 %), `ruff check`/`format --check` чисто; `promtool check config` — SUCCESS (1 rule file, 11 rules). T2.1 ✅; T2.2 (дашборд) и T3.1 (алерты + приёмник) остаются ⬜ | `a441541` |
| 2026-11-16 | T2.2 | Дашборд Grafana как код: `observability/grafana/dashboards/clikit-cloud.json` (UID `clikit-cloud`, 13 панелей: RPS, 5xx, доступность/бюджет за 30 дней, burn rate 1ч/6ч, in-flight, RPS по маршрутам, p50/p95/p99, пул БД, CPU/RAM хоста, up, логи Loki; переменная маршрута, `editable: false`), provisioning read-only из Git. Скриншот `docs/img/screenshot-dashboard.png` добавлен в README (EN/RU), раздел «Наблюдаемость» и чекпоинт в `docs/observability.md` §4.1. Попутно исправлены recording rules T0.1: при существующих счётчиках с нулевым `rate` знаменатель SLI давал `NaN` — добавлено `> 0` и внешний `or vector(...)`; новый promtool-сценарий падает на старых правилах и проходит на новых (проверено оба). `promtool check rules` — 11 rules, `test rules` — SUCCESS (5 сценариев). Живой чекпоинт: дашборд в `/api/dashboards/uid/clikit-cloud` (13 панелей), 8/8 targets UP, панели показывают трафик, SLI = 1, burn rate = 0 (после перезапуска Prometheus с чистым TSDB). Тесты: 9 новых `tests/service/test_grafana_dashboard.py`; полный прогон **603 passed**, `ruff check`/`format --check` чисто | `3101ec2` |
| 2026-11-16 | T3.1 | Алерты и Alertmanager: `observability/prometheus/alerts.yml` — 7 правил в 3 группах (`ClikitApiDown` 1 мин, `FastErrorBudgetBurn` 14.4/1ч, `SlowErrorBudgetBurn` 6/6ч, `High5xxRate` > 1 %/5 мин, `HighScenarioLatency` p95 > 300 мс/10 мин, `DbPoolExhausted` in_use ≥ 5, `HostMemoryLow` < 10 %); новая recording rule `clikit:sli_latency:p95_rate5m` (12 записей всего, ADR №66), чтобы алерт не дублировал `histogram_quantile`. Alertmanager: маршрутизация по severity (critical — repeat 1 ч, warning — 4 ч, оба в `local-sink` с `send_resolved: true`) и inhibition: `ClikitApiDown` подавляет 5 из 6 алертов-следствий. `prometheus.yml` грузит оба файла правил; CI-job `observability-rules` гоняет `promtool check rules` (12 + 7 rules) и оба `test rules` на `prom/prometheus:v3.16.0`. promtool-сценарии `tests/alerts_test.yml` (6: падение API с firing→resolved, 5xx, p95, burn rate, пул, память) и 12 статических тестов `tests/service/test_alerts.py`; обновлены `test_slo_docs.py`, `test_observability_stack.py`, `docs/sre/slo.md` §11 и `docs/observability.md` §5.4/§7. Живой чекпоинт: reload Prometheus/Alertmanager → 12 recording + 7 alerting rules загружены; `docker compose stop api` → `ClikitApiDown` pending (30–75 с) → **firing** (~90 с), виден в `/api/v1/alerts`, Alertmanager и в `GET /alerts` приёмника (`severity=critical`); `start api` → промет `up=1`, алерт исчез из Prometheus (~30 с), приёмник получил **resolved**; inhibition проверен статическими тестами. Полный прогон **614 passed**, `ruff check`/`format --check` чисто | `57323a1` |
| 2026-11-21 | T3.2 | Runbook и постмортем: `docs/sre/runbook.md` — 8 сценариев (ClikitApiDown, 5xx/быстрый burn, latency, пул БД, память хоста, медленный burn, диск, падение пайплайна релиза) с «первыми 3 минутами», копируемыми командами, критерием восстановления и правилами «сначала улики, потом рестарт»; пороги не дублируются — ссылки на `slo.md` и `alerts.yml`. `docs/sre/postmortem-template.md` — blameless-шаблон (метаданные, таймлайн UTC, влияние, причины + 5 why, действия с владельцем/сроком/типом, уроки, чек-лист). `docs/sre/postmortems/2026-10-29-release-pipeline.md` — реальный разбор по фактам GitHub Actions: прогоны 40934279478 и 40936253756 (`нет файла: dist\NOTICE.txt` — `build_exe.py --zip` клал NOTICE внутрь onedir, локально маскировалось остатком от `--onefile`), 40937694525 (`no matches found for assets/ClicKit-win64.zip` — `upload-artifact` сохранил префикс `dist/`), успешный 40944319704; коммиты `02d873c`, `c54db02`; открытые действия A4/A5/A7 помечены `⬜`. Попутно `docs/observability.md` §8, `docs/cloud.md` §10, README (EN/RU) и `slo.md` связаны с runbook. Тесты: 9 новых `tests/service/test_runbook.py` (покрытие всех 7 алертов, ≥5 сценариев, живые ссылки, факты прогонов, владельцы действий, отсутствие секретов); `ruff` чисто | `4c7de57` |
| 2026-11-21 | T4.1 | SLO/error budget и burn rate: `observability/prometheus/recording_rules.yml` — `remaining_ratio_30d` (`1 − consumed`), `remaining_minutes_30d` (`(1 − consumed) · 216`, где 216 = 30 дней · 0.5 %) и `policy_state_30d` — режим политики §7 меткой `state` (`normal` < 50 %, `careful` 50–75 %, `freeze` 75–100 %, `exhausted` ≥ 100 %), значение `1` (`count by (state)`), чтобы режим нельзя было спутать с процентом бюджета. `alerts.yml` — группа `clikit-error-budget`: `ErrorBudgetFreeze` (≥ 0.75, warning, `for` 10 мин) и `ErrorBudgetExhausted` (≥ 1, critical, `for` 10 мин); оба читают `consumed_ratio_30d` и **не подавляются** `ClikitApiDown` (простой API сам жжёт бюджет). `scripts/slo_report.py` — отчёт в терминале (`--json`, `--prometheus-url`/`$CLICKIT_PROMETHEUS_URL`): доступность, % бюджета, остаток («3 ч 36 мин»), режим и burn rate; коды выхода 0/1/2/3 — задел для гейта деплоя M10 («нет данных» ≠ «всё хорошо»). promtool: 6 новых сценариев в `slo_rules_test.yml` (0.2/0.3/0.4/1 % ошибок → 129.6/86.4/43.2/−216 мин и `normal`/`careful`/`freeze`/`exhausted`, пустой трафик → 216 мин, `normal`) и 3 в `alerts_test.yml` (60 % — тишина, 80 % — только `ErrorBudgetFreeze`, 100 % — `ErrorBudgetExhausted`). Дашборд: панель остатка переведена на запись в минутах, добавлена панель «Режим политики бюджета» (14 панелей). Документация: `docs/sre/slo.md` §6.1/§7/§8/§9/§11, `docs/sre/runbook.md` §11 «Политика бюджета: заморозка и нарушение SLO», `docs/observability.md` §5.4/§5.5, README (EN/RU), ADR №68. Живой чекпоинт на поднятом стеке: reload Prometheus → 15 записей + 9 алертов загружены, `remaining_minutes_30d = 216`, `policy_state_30d{state="normal"} = 1`, `slo_report.py` печатает «3 ч 36 мин», `normal`, код 0; дашборд отдаёт 14 панелей с новыми записями. Тесты: 38 новых `tests/service/test_slo_report.py`, обновлены `test_slo_docs.py`/`test_alerts.py`/`test_grafana_dashboard.py`/`test_runbook.py`; service — 388 passed, полный прогон **662 passed** (покрытие сервиса 95.04 %); `ruff check`/`format --check` чисто; `promtool check rules` (15 + 9) и оба `test rules` — `SUCCESS`. При оформлении PR проверка срабатывания `ErrorBudgetFreeze`/`ErrorBudgetExhausted` перенесена с 11m на 13m: 11m — ровно граница `for: 10m`, и promtool флаковал из-за порядка вычисления групп правил. | `d8d609d` |
| 2026-11-21 | T5.1 | Демо «сломай и почини»: `docs/observability-demo.md` — пошаговый сценарий на 5 минут (признаки жизни: лог/метрика/трейс; `stop api` → `pending` → `firing` в Prometheus/Alertmanager/приёмнике → разбор по `runbook.md` §3 без чтения исходников → `start api` → `resolved` → `slo_report.py`), таблица «что доказывает демо», §5 «чего демо не показывает» и §6 диагностика; честно зафиксировано слепое пятно SLI (падение API не видно в error budget — `slo.md` §3, демо показывает это на экране). `scripts/observability_demo.py` — исполняемая версия: подкоманды `check` (готовность: `compose config` + 8/8 targets + `/healthz`) и `run` (полный контур, опрос `/api/v1/alerts` → `/api/v2/alerts` → `/alerts` до фактического `firing`/`resolved`, без «спать 90 секунд»), таймлайн с отметками времени, `--json`, коды выхода 0/1/2 и аварийное восстановление API в `finally` (сервис нельзя оставлять выключенным). Живой прогон: `ДЕМО ПРОЙДЕНО за 1 мин 48 с`, 8/8 проверок OK, «8/8 targets UP», `firing` через 1 мин 17 с (`for: 1m` + скрейп + оценка), `resolved` через 22 с после возврата API, error budget `normal`/216 мин; провальный прогон `--timeout 4` → код 1 и `start api` в таймлайне. Обновлены `docs/observability.md` (новый §8 «Демо»), `docs/sre/runbook.md` §13/§14, README (EN/RU), ADR №69. Тесты: 29 новых `tests/service/test_observability_demo.py` (связь алерта/целей/таймаута с `alerts.yml`/`prometheus.yml`, разбор ответов трёх сервисов, ожидание с временными ошибками, коды выхода, аварийное восстановление, отсутствие секретов); service — 416 passed, `ruff check`/`format --check` чисто | `d0c291e`, PR #11 |
| 2026-11-21 | — | Веха M8 закрыта: PR #11 влит в `master` (`4b6d101`), 7/7 проверок CI зелёные (ruff, тесты 3.11–3.13, service + PostgreSQL 16, Docker Linux, promtool), все 10 задач ✅. Попутно исправлена нумерация ADR демо: в плане стояло №70, в реестре `AI_CONTEXT.md` §3.3 — №69 (№70 не существует) | `4b6d101` |

## 11. Вне вехи

- Managed-мониторинг облака, синтетические проверки из разных регионов.
- Долгосрочное хранилище метрик (Thanos/VictoriaMetrics), HA Prometheus.
- APM-профилирование, continuous profiling, eBPF.
- PagerDuty/Telegram-интеграции с реальным on-call (M11 — учебные учения).
