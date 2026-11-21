# Демо наблюдаемости «сломай и почини»

> Практическое упражнение на 5 минут: сломать ClicKit Cloud, увидеть алерт,
> разобрать причину по логам/метрикам/трейсу и восстановить сервис. Сценарий
> проверяет весь контур `лог → метрика → алерт → runbook → SLO` (T5.1), а не
> отдельные компоненты стека.
> Нормативные документы: [`docs/observability.md`](observability.md) — запуск
> стека, [`docs/sre/slo.md`](sre/slo.md) — цифры SLO,
> [`docs/sre/runbook.md`](sre/runbook.md) §3 — действия при `ClikitApiDown`.
> Цель упражнения — приёмка плана M8: инцидент разбирается без чтения
> исходников, а алерт приходит раньше, чем пользователи массово видят ошибки.

## 1. Что доказывает демо

| Шаг | Что происходит | Где это видно |
|---|---|---|
| Трафик | `GET /v1/scenarios` пишет метрику, JSON-лог и спан БД | `/metrics`, Loki, Tempo |
| Поломка | `docker compose stop api` — API не отвечает | `up == 0` в Prometheus |
| Алерт | `ClikitApiDown` переходит `pending → firing` | Prometheus, Alertmanager, приёмник |
| Разбор | `ps`, `logs`, `/healthz`, `/readyz` по runbook §3 | терминал, Loki |
| Починка | `docker compose start api` | `/healthz` 200, `up == 1` |
| Закрытие | `ClikitApiDown` исчезает, приёмник получает `resolved` | Prometheus, Alertmanager |
| Бюджет | `slo_report.py` показывает режим и остаток | терминал, дашборд |

### 1.1. Важная честность про SLI

Падение API **не видно в SLI доступности** ([`slo.md`](sre/slo.md) §3):
SLI считает долю успешных ответов среди запросов, дошедших до приложения. Если
запросы не доходят, знаменатель пуст, а пустой трафик по контракту SLO
считается выполнением. Поэтому:

- падение ловит только `up{job="clikit-api"} == 0` — отдельный алерт
  `ClikitApiDown`, а не SLI;
- `python scripts/slo_report.py` во время простоя покажет `normal` и целый
  бюджет: простой не «сжигает» бюджет, но и **не** означает «всё хорошо».
  Именно поэтому есть алерт, а не только отчёт по бюджету.

Демо специально показывает это на экране — вместо того чтобы делать вид, что
SLI видит всё.

## 2. Что понадобится

| Требование | Проверка |
|---|---|
| Docker Desktop (Linux-контейнеры), Compose ≥ 2.20 | `docker compose version` |
| ~2 ГБ свободной ОЗУ | лимиты контейнеров заданы в compose |
| `.env` с `CLICKIT_API_KEY` и `POSTGRES_PASSWORD` | `Copy-Item .env.example .env` |
| Свободные порты 8000, 3000, 8080, 9090, 9093, 3100, 3200 | `docs/observability.md` §3.1 |

Стек — из Git, руками в UI ничего не настраивается (ADR №39, №65):
дашборд `clikit-cloud.json`, правила и datasource приходят из репозитория.

## 3. Ручной сценарий на 5 минут

Все команды — из корня репозитория. Время в скобках — реальный замер на
ноутбуке (2026-11-21), а не оценка: у вас будет близко, но не идентично.

### 3.1. Подготовка (~60 с, первый запуск — дольше)

```powershell
Copy-Item .env.example .env
# заполните CLICKIT_API_KEY (>= 16 символов) и POSTGRES_PASSWORD
docker compose -f docker-compose.observability.yml up -d --build
python scripts/observability_demo.py check
```

Ожидаемый вывод `check` — стек готов к демо:

```text
[      0 с] стек готов: 8/8 targets UP
[      0 с] API отвечает: GET /healthz → 200
Стек готов к демо. Запуск: python scripts/observability_demo.py run
```

`check` не просто смотрит порты: он подтверждает, что `docker compose config`
читает `.env`, и что все **8** целей в Prometheus `up` (см.
`docs/observability.md` §4).

### 3.2. Признаки жизни: лог, метрика, трейс (~30 с)

```powershell
curl.exe -s -o NUL -w "%{http_code}`n" "http://127.0.0.1:8000/v1/scenarios?limit=1"
curl.exe -s "http://127.0.0.1:9090/api/v1/query?query=clikit_http_requests_total" |
  ConvertFrom-Json | ForEach-Object { $_.data.result } |
  Select-Object @{n='route';e={$_.metric.route}}, @{n='status';e={$_.metric.status}},
                @{n='count';e={$_.value[1]}}
```

Ответ `200` означает, что запрос дошёл; счётчик `route="/v1/scenarios"` растёт.
В Grafana → Explore → Loki поток `{service="api"}` содержит JSON-строку с
`request_id` и `trace_id`; в Explore → Tempo по этому `trace_id` виден HTTP-спан
и дочерние спаны SQL (ADR №41, №63).

### 3.3. Ломаем (~5 с): `stop api`

```powershell
docker compose -f docker-compose.observability.yml stop api
```

Проверьте, что сервис действительно лёг:

```powershell
curl.exe -s -o NUL -w "%{http_code}`n" http://127.0.0.1:8000/healthz   # не 200
```

Обратите внимание: **специально не чиним сразу**. Инцидент начинается не с
рестарта, а с наблюдения (runbook §1.2: сначала улики, потом лечение).

### 3.4. Ждём алерт (~90 с): `pending → firing`

`ClikitApiDown` = `up{job="clikit-api"} == 0` с `for: 1m`. Скрейп 15 с и
оценка правил 15 с добавляют задержку, поэтому `firing` приходит не через 60 с,
а примерно через **85–90 с** после остановки.

```powershell
# 1. Состояние алерта в Prometheus: pending → firing
Invoke-RestMethod "http://127.0.0.1:9090/api/v1/alerts" |
  ForEach-Object { $_.data.alerts } |
  Select-Object @{n='alert';e={$_.labels.alertname}}, state, @{n='since';e={$_.activeAt}}

# 2. Alertmanager принял (severity=critical)
Invoke-RestMethod "http://127.0.0.1:9093/api/v2/alerts" |
  Select-Object @{n='alert';e={$_.labels.alertname}}, @{n='state';e={$_.status.state}}

# 3. Локальный приёмник получил вебхук
Invoke-RestMethod http://127.0.0.1:8080/alerts | ConvertTo-Json -Depth 5
```

Что должно быть видно: `state = firing` в Prometheus, `state = active` в
Alertmanager и запись `[firing] ClikitApiDown (severity=critical)` в приёмнике.
Следствия (`High5xxRate`, латентность, пул БД) подавлены inhibition — разбирать
их не нужно, пока активен `ClikitApiDown`.

### 3.5. Разбор по runbook (~60 с), без чтения исходников

Действия — [`docs/sre/runbook.md`](sre/runbook.md) §3. Минимальный набор:

```powershell
docker compose -f docker-compose.observability.yml ps                       # api: Exited
docker compose -f docker-compose.observability.yml logs --tail=50 api       # причина
docker compose -f docker-compose.observability.yml ps db migrate            # БД и миграции
docker compose -f docker-compose.observability.yml logs --tail=20 alert-sink
```

В этом демо контейнер просто остановлен, поэтому `logs api` показывает штатное
завершение, а не ошибку — и это тоже полезный вывод: метрика говорит «цель
недоступна», а журнал уточняет, что сервис не падал внутри. В реальном
инциденте здесь были бы `Application startup failed`, OOM или traceback с
`request_id`.

### 3.6. Чиним (~10 с): `start api`

```powershell
docker compose -f docker-compose.observability.yml start api
docker compose -f docker-compose.observability.yml ps api        # healthy
curl.exe -s -o NUL -w "%{http_code}`n" http://127.0.0.1:8000/healthz   # 200
```

### 3.7. Закрываем (~60 с): `resolved`

Когда Prometheus снова получает `up = 1`, условие алерта ложно и он исчезает
из `/api/v1/alerts`; Alertmanager отправляет `resolved` в приёмник
(`send_resolved: true`).

```powershell
Invoke-RestMethod "http://127.0.0.1:9090/api/v1/alerts" | ForEach-Object { $_.data.alerts }  # пусто
Invoke-RestMethod http://127.0.0.1:8080/alerts | ConvertTo-Json -Depth 5
```

Критерий закрытия (runbook §12): алерт в `resolved`, `slo_report.py` возвращает
код `0`, причина устранена, а не замаскирована рестартом.

### 3.8. Замыкаем контур: error budget (~15 с)

```powershell
python scripts/slo_report.py
```

Ожидаемо: `режим политики: normal`, остаток `216.0 мин` и код выхода `0` —
падение API не отражено в SLI (см. §1.1). Для алерта `ClikitApiDown` это
нормально; если бы бюджет жёгся, отчёт показал бы `freeze`/`exhausted`.

### 3.9. Уборка

```powershell
docker compose -f docker-compose.observability.yml down       # данные сохраняются
# docker compose -f docker-compose.observability.yml down -v  # удалить данные (необратимо)
```

## 4. Автоматическая версия

Скрипт делает те же шаги и **не гадает по времени**: он опрашивает
`/api/v1/alerts`, `/api/v2/alerts` и `/alerts` приёмника, пока состояние не
наступит, и только потом идёт дальше.

```powershell
python scripts/observability_demo.py check    # готов ли стек (код 0/2)
python scripts/observability_demo.py run      # полный сценарий (~2 мин, код 0/1/2)
python scripts/observability_demo.py run --json
python scripts/observability_demo.py run --timeout 300   # если машина медленная
```

Реальный вывод прогона 2026-11-21 (сокращённо, с отметками времени):

```text
[      0 с] стек готов: 8/8 targets UP
[      0 с] API отвечает: GET /healthz → 200
[      0 с] трафик: GET /v1/scenarios → 200; clikit_http_requests_total = 59
[      2 с] сломали: docker compose stop api
[     18 с] Prometheus: ClikitApiDown pending
[1 мин 18 с] Prometheus: ClikitApiDown firing через 1 мин 17 с (for: 1m + скрейп + оценка правил)
[1 мин 18 с] Alertmanager: алерт принят через 0 с
[1 мин 18 с] приёмник: [firing] ClikitApiDown через 0 с (записей: 2)
[1 мин 22 с] чиним: docker compose start api
[1 мин 26 с] API снова отвечает через 4 с
[1 мин 48 с] Prometheus: алерт исчез через 22 с
[1 мин 48 с] Alertmanager: алерт снят через 0 с
[1 мин 48 с] приёмник: [resolved] ClikitApiDown через 0 с (записей: 2)
[1 мин 48 с] error budget: режим normal, остаток 216.0 мин (падение API не видно в SLI — docs/sre/slo.md §3)
```

Итог: **8 проверок**, `ДЕМО ПРОЙДЕНО за 1 мин 48 с`, код выхода `0`.
Полный сценарий укладывается в 5 минут вместе с подъёмом стека на тёплой машине
(первый `up -d --build` дольше: собирается образ сервиса).

Коды выхода скрипта: `0` — демо пройдено, `1` — шаг не уложился в таймаут,
`2` — стек не готов (нет `.env`, цели DOWN, Docker недоступен). Скрипт всегда
возвращает API в строй, даже если упал между поломкой и починкой: оставлять
сервис выключенным после демонстрации нельзя (runbook §1.2).

## 5. Чего демо не показывает

Честные границы — часть документа, а не мелкий шрифт:

- **5xx и латентность** не генерируются: сценарий `High5xxRate` /
  `HighScenarioLatency` проверяется promtool-сценариями и ручным разбором
  runbook §4–§5, а не этим демо. Сделать искусственные 500 без «тестового
  режима» в сервисе — значит добавить в продукт дыру ради демо.
- **SLI слеп к полному падению** (см. §1.1) — демо показывает это, а не
  маскирует.
- **Нет реальных клиентов**: пустой трафик по контракту SLO — выполнение,
  поэтому отчёт по бюджету в демо остаётся `normal`.
- **Один инстанс и один приёмник**: HA Prometheus и PagerDuty — вне M8
  (`plans/M8-observability.md` §11); настоящий on-call — учения M11.
- **Loki/Tempo только для чтения**: демо проверяет, что след запроса есть, но
  не подменяет нагрузочное или chaos-тестирование.

## 6. Если что-то пошло не так

| Симптом | Причина и решение |
|---|---|
| `check` → код 2, `compose-файл не читается: ... POSTGRES_PASSWORD` | Нет `.env` или в нём пустые секреты: `Copy-Item .env.example .env`, заполнить, повторить. |
| `check` → код 2, `стек наблюдаемости не поднят` | Стек не запущен: `docker compose -f docker-compose.observability.yml up -d --build`. |
| `не UP targets: clikit-api` | `migrate` не завершился или API падает на старте: `ps`, `logs api`, `logs migrate` (`docs/observability.md` §7). |
| `ClikitApiDown` не появился за 4 минуты | Prometheus не видит `up == 0`: правила загружены? `curl.exe -s http://127.0.0.1:9090/api/v1/rules`. Проверьте `alerts.yml` в `/etc/prometheus` и `--web.enable-lifecycle`. |
| `firing` есть, в Alertmanager пусто | Alertmanager не подключён: `curl.exe -s http://127.0.0.1:9090/api/v1/alertmanagers`; смотрите `logs alertmanager`. |
| Приёмник пуст, Alertmanager полон | Вебхук не доставлен: `logs alert-sink`, проверьте `webhook_configs[].url` в `alertmanager.yml`. |
| `resolved` не пришёл | Prometheus должен снова видеть `up = 1`; Alertmanager шлёт `resolved` с `group_interval` (critical — 30 с). |
| Демо упало посередине | Скрипт сам выполняет `start api`; проверьте `ps api` и при необходимости `restart api`. |

## 7. Связанные документы

- [`docs/observability.md`](observability.md) — запуск стека, targets, §5.4
  чекпоинт алертов, §7 диагностика.
- [`docs/sre/runbook.md`](sre/runbook.md) — процедура по каждому алерту (§3 —
  `ClikitApiDown`), §13 — как проверяется сам runbook.
- [`docs/sre/slo.md`](sre/slo.md) — SLI/SLO, error budget, политика §7.
- [`docs/sre/postmortem-template.md`](sre/postmortem-template.md) — если демо
  превратилось в инцидент (или в M11 будет учебный инцидент).
- `scripts/observability_demo.py` — исполняемая версия сценария;
  `tests/service/test_observability_demo.py` — статические и unit-проверки.
