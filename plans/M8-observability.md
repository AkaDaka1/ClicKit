# M8 — Наблюдаемость и SLO

> План создан 2026-11-01. Статус: 📋 запланировано.
> Зависимость: M7 (работающий сервис и БД). Без сервиса метрикам нечего
> измерять; M8 не добавляет новые продуктовые функции.

## 1. Цель

Сделать ClicKit Cloud наблюдаемым и управляемым по надёжности: понять, что
происходит с сервисом в любой момент, увидеть деградацию до жалоб
пользователей и иметь измеримый ответ на вопрос «мы выполняем обещания?».

Результат вехи — не «галочки про Prometheus», а полный контур:
**лог → метрика → алерт → runbook → SLO → постмортем**.

## 2. Критерий готовности

- [ ] В логах JSON с `request_id` и `trace_id`; секреты и API-ключи не пишутся.
- [ ] `GET /metrics` отдаёт `clikit_http_requests_total`,
      `clikit_http_request_duration_seconds` (гистограмма),
      `clikit_http_requests_in_flight`, `clikit_db_pool_connections`,
      `clikit_build_info`.
- [ ] Трейс запроса виден в Tempo: спаны HTTP и запроса к БД; `trace_id`
      из трейса совпадает с логом.
- [ ] `docker compose -f docker-compose.observability.yml up -d` поднимает
      Prometheus, Grafana, Loki, Promtail, Tempo, Alertmanager.
- [ ] Дашборд Grafana хранится JSON-файлом в репозитории: RPS, error rate,
      p50/p95/p99, in-flight, БД, CPU/RAM; скриншот — в README.
- [ ] Алерты: 5xx > 1% за 5 мин, p95 > 300 мс за 10 мин, target down 1 мин,
      быстрый/медленный burn rate error budget, пул БД, память.
- [ ] `stop api` → алерт переходит в firing и виден в Alertmanager/приёмнике;
      возврат сервиса → resolved.
- [ ] `docs/sre/slo.md`: SLI, SLO 99.5%, error budget, окно 30 дней,
      политика исчерпания бюджета; `docs/sre/runbook.md` — минимум 5 сценариев.
- [ ] Реальный постмортем по инциденту релиза 2026-10-29 и шаблон постмортема.
- [ ] `promtool check rules` и `promtool test rules` зелёные; JSON-логи
      проверяются тестом схемы.

## 3. Согласованные параметры

| Параметр | Решение |
|---|---|
| SLO доступности | 99.5% за 30 дней; error budget 0.5% ≈ 3 ч 36 мин |
| SLO latency | p95 ≤ 300 мс для успешных `GET /v1/scenarios/{id}` и `POST /v1/scenarios` |
| SLI | доля успешных ответов (2xx/3xx) от всех, кроме 4xx клиента; latency по 2xx/3xx |
| Окно | 30 дней, rolling; быстрый burn rate — 1 ч, медленный — 6 ч |
| Скрап | Prometheus каждые 15 с, retention 15 дней локально |
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
- `service/app/observability/tracing.py` — OTel, FastAPI/SQLAlchemy
  instrumentation, OTLP-экспортёр.
- middleware: `X-Request-ID` (входящий или новый), запись в лог и ответ.

### 4.2. Инфраструктура наблюдаемости

```
observability/
├── prometheus/
│   ├── prometheus.yml
│   ├── alerts.yml
│   └── recording_rules.yml
├── alertmanager/alertmanager.yml
├── grafana/
│   ├── provisioning/datasources/datasources.yml
│   ├── provisioning/dashboards/dashboards.yml
│   └── dashboards/clikit-cloud.json
├── loki/loki-config.yml
├── promtail/promtail-config.yml
└── tempo/tempo.yml
docker-compose.observability.yml
scripts/alert_sink.py        # локальный приёмник вебхуков Alertmanager
```

### 4.3. Документы

- `docs/sre/slo.md` — SLI/SLO, окно, error budget, burn rate, политика.
- `docs/sre/sla.md` — чем SLA отличается от SLO; для пет-проекта — внутренний SLA.
- `docs/sre/runbook.md` — сервис недоступен, высокий 5xx, latency, БД, диск.
- `docs/sre/postmortem-template.md` — blameless-шаблон.
- `docs/sre/postmortems/2026-10-29-release-pipeline.md` — реальный разбор
  трёх упавших прогонов `Release` и фикса путей `NOTICE.txt`.

## 5. Решения (ADR; итог — в `AI_CONTEXT.md` §3.3)

- **ADR №39 — стандартный стек наблюдаемости.** Prometheus + Grafana + Loki +
  Tempo + Alertmanager: минимальный набор, покрывающий метрики, логи, трейсы
  и алерты, без ELK/Kafka/Istio. Дашборды и правила — в Git.
- **ADR №40 — SLO как контракт с самим собой.** SLO 99.5% и error budget
  фиксируются до оптимизаций; измерения — по фактическому трафику, а не
  «на глаз». Исчерпание бюджета останавливает рискованные изменения.
- **ADR №41 — корреляция через request_id/trace_id.** Один идентификатор
  проходит HTTP → лог → трейс; без него разбор инцидента снова ручной.

## 6. Граф задач

| ID | Задача | Зависимости | Чекпоинт (done = …) | Статус |
|---|---|---|---|---|
| T0.1 | SLI/SLO и PromQL-запросы, политика error budget | M7 | `docs/sre/slo.md` с формулами и цифрами; запросы проверены | ⬜ |
| T1.1 | JSON-логи и `request_id` middleware | T0.1 | Логи парсятся, поля обязательны, секретов нет | ⬜ |
| T1.2 | Prometheus-метрики и `/metrics` | T1.1 | Метрики scrapes, unit-тесты, имена стабильны | ⬜ |
| T1.3 | OTel-трейсы и Tempo | T1.2 | Спан HTTP + БД, `trace_id` в логе | ⬜ |
| T2.1 | Compose-стек наблюдаемости | T1.3 | Все targets UP, UI открываются | ⬜ |
| T2.2 | Дашборд Grafana как код | T2.1 | JSON в Git, панели показывают трафик, скриншот | ⬜ |
| T3.1 | Алерты и Alertmanager + приёмник | T2.2 | `stop api` → firing → resolved; `promtool test rules` | ⬜ |
| T3.2 | Runbook и постмортем | T3.1 | 5 сценариев + реальный постмортем | ⬜ |
| T4.1 | SLO/error budget и burn rate | T3.2 | Политика, алерты, расчёт на 30 дней | ⬜ |
| T5.1 | Демо «сломай и почини» + README | T4.1 | 5-минутный сценарий воспроизводим с чистой машины | ⬜ |

### Волны

```
Волна 1: T0.1
Волна 2: T1.1 → T1.2 → T1.3
Волна 3: T2.1 → T2.2
Волна 4: T3.1 → T3.2
Волна 5: T4.1 → T5.1
```

## 7. Список коммитов

1. `docs: план M8 — наблюдаемость и SLO` (T0.1)
2. `feat: JSON-логи и request_id` (T1.1)
3. `feat: метрики Prometheus в сервисе` (T1.2)
4. `feat: трейсы OpenTelemetry` (T1.3)
5. `feat: compose-стек наблюдаемости` (T2.1)
6. `feat: дашборд Grafana как код` (T2.2)
7. `feat: алерты и Alertmanager` (T3.1)
8. `docs: runbook и постмортем` (T3.2)
9. `docs: SLO и error budget` (T4.1)
10. `docs: демо наблюдаемости` (T5.1)

## 8. Чек-лист приёмки

- [ ] Инцидент «сервис упал» разбирается по логам, метрикам и трейсу без
      чтения исходников.
- [ ] Алерт срабатывает до того, как пользователь массово видит ошибки.
- [ ] В SLO-документе есть цифры, окно, бюджет и правило действий.
- [ ] Дашборд и правила восстанавливаются из Git, а не «руками в UI».
- [ ] Постмортем blameless: факты, таймлайн, причины, действия, владельцы.
- [ ] M7-функциональность не сломана; тесты сервиса зелёные.

## 9. Риски и меры

| Риск | Мера |
|---|---|
| Стек наблюдаемости «съест» память ноутбука | Лимиты контейнеров, retention 15 дней, профиль `observability` в compose |
| Кардинальность меток взорвётся | Метки только `method`, `route`, `status`; без id и query-параметров |
| Логи с PII/секретами | Явный allowlist полей, тест схемы, gitleaks в M11 |
| Алерты шумят | `for`, severity, burn rate; тесты правил; подавление дублей |
| SLO выдуман | Сначала измерить трафик, затем зафиксировать; пересмотр раз в квартал |

## 10. Журнал задач

| Дата | Задача | Результат | Commit |
|---|---|---|---|
| 2026-11-01 | — | План создан; SLO и стек согласованы | — |

## 11. Вне вехи

- Managed-мониторинг облака, синтетические проверки из разных регионов.
- Долгосрочное хранилище метрик (Thanos/VictoriaMetrics), HA Prometheus.
- APM-профилирование, continuous profiling, eBPF.
- PagerDuty/Telegram-интеграции с реальным on-call (M11 — учебные учения).



