# M10 — Непрерывная доставка

> План создан 2026-11-01. Статус: 📋 запланировано.
> Зависимости: M9 (кластер и Helm-чарт), M7 (образ сервиса), M6 T3.2
> (механизм публикации образов в GHCR). M10 не дублирует M6 T5.1:
> там — draft-релиз desktop-приложения, здесь — деплой сервиса в кластер.

## 1. Цель

Сделать доставку изменений сервиса предсказуемой: merge в `master`
автоматически доезжает до staging, production требует подтверждения,
провал проверки откатывается без ручного «поднимать руками». Плюс измерять
доставку в терминах DORA, а не «кажется, стало быстрее».

## 2. Критерий готовности

- [ ] Образ сервиса публикуется в GHCR с тегами `<sha>` и `latest`;
      деплой использует digest, а не плавающий `latest`.
- [ ] Merge в `master` → staging обновляется автоматически; smoke-тесты
      (`/healthz`, `/readyz`, `/version`, `/metrics`, CRUD сценария) зелёные.
- [ ] Production — только через GitHub Environment с обязательным ревьюером;
      после деплоя те же smoke-тесты.
- [ ] «Плохой» образ (не проходит smoke) автоматически откатывается
      `helm rollback`; сервис возвращается к предыдущей ревизии.
- [ ] Секреты (kubeconfig, DB password, API key) — только в GitHub
      Environments, не в репозитории и не в логах.
- [ ] `scripts/dora_metrics.py` считает deployment frequency, lead time,
      change failure rate и MTTR по данным GitHub; цифры за 30 дней в
      `docs/sre/dora.md`.
- [ ] `docs/cd.md` и runbook «деплой/откат» позволяют повторить операцию
      за 10 минут без автора.

## 3. Согласованные параметры

| Параметр | Решение |
|---|---|
| Триггер staging | push в `master` |
| Триггер production | ручной `workflow_dispatch` + approval Environment `production` |
| Теги образов | `sha-<short>` и `latest`; деплой по digest |
| Релизы сервиса | тег `cloud-v<semver>` (не пересекается с desktop `v*`) |
| Инструмент деплоя | `helm upgrade --install --atomic --wait --timeout 5m` |
| Namespaces | `clikit-staging`, `clikit-prod` в одном кластере (экономия); БД — отдельные базы |
| Откат | `helm rollback <release> <revision>`; скрипт `scripts/rollback.sh` |
| Smoke | Python-скрипт на `httpx`, 6 проверок, exit code ≠ 0 при провале |
| DORA | окно 30 дней; источник — GitHub API (workflow runs, deployments, issues) |
| Ограничение | Один кластер и одна БД на два окружения — осознанная экономия; production-изоляция описана в `docs/cd.md` |

## 4. Модули и интерфейсы

```
.github/workflows/
├── cd.yml                 # build → scan → push → deploy staging → smoke
└── cd-prod.yml            # ручной запуск + approval → deploy prod → smoke
deploy/helm/clikit-cloud/
├── values-staging.yaml
└── values-prod.yaml
scripts/
├── smoke_service.py       # 6 проверок против URL
├── rollback.sh            # helm rollback + smoke
└── dora_metrics.py        # DORA за окно, JSON/Markdown
docs/cd.md
docs/sre/dora.md
docs/sre/runbooks/deploy.md
```

### 4.1. `cd.yml`

1. checkout + setup buildx.
2. build образа из `docker/Dockerfile.service`, теги `sha-<short>`, `latest`.
3. push в GHCR (использует паттерн M6 T3.2; отдельный образ `clikit-cloud`).
4. `helm upgrade --install clikit-staging ... --set image.digest=sha256:...`.
5. `kubectl rollout status` + `smoke_service.py`.
6. при ошибке — `helm rollback` и красный job.

### 4.2. `cd-prod.yml`

- `workflow_dispatch` с input `image_digest` (по умолчанию — последний staging).
- Environment `production` с required reviewer.
- Тот же чарт с `values-prod.yaml`; smoke; откат при провале.
- Параллельный деплой staging и prod запрещён `concurrency`.

### 4.3. Smoke-проверки

1. `/healthz` → 200.
2. `/readyz` → 200.
3. `/version` содержит ожидаемый git sha.
4. `/metrics` содержит `clikit_build_info`.
5. `POST /v1/scenarios` с временным ключом → 201.
6. `GET /v1/scenarios/{id}` → 200 и совпадает `sha256`; затем `DELETE` → 204.

### 4.4. DORA

- Deployment frequency — число успешных деплоев / неделя.
- Lead time — медиана от коммита до успешного деплоя.
- Change failure rate — доля деплоев, потребовавших отката/фикса.
- MTTR — медиана от «deploy failed/incident opened» до восстановления.
- Скрипт печатает Markdown-таблицу и JSON; цифры фиксируются в `docs/sre/dora.md`.

## 5. Решения (ADR; итог — в `AI_CONTEXT.md` §3.3)

- **ADR №45 — доставка по digest, а не по `latest`.** Плавающий тег делает
  деплой невоспроизводимым; digest фиксирует конкретный образ и позволяет
  точно откатиться.
- **ADR №46 — staging автоматически, production с approval.** Это дешёвая
  модель разделения ответственности: рутинные изменения не ждут человека,
  рискованные — требуют явного решения.
- **ADR №47 — откат как штатная операция.** `helm rollback` и smoke-тесты
  встроены в пайплайн; откат проверяется намеренно «плохим» образом, а не
  остаётся теорией.

## 6. Граф задач

| ID | Задача | Зависимости | Чекпоинт (done = …) | Статус |
|---|---|---|---|---|
| T0.1 | Environments, namespaces, service account, секреты | M9 | `kubectl get ns`; GitHub Environments созданы | ⬜ |
| T1.1 | Публикация образа сервиса в GHCR | T0.1, M6 T3.2 | Образ `sha` + `latest` доступен, digest записан | ⬜ |
| T1.2 | Деплой в staging и smoke | T1.1 | Merge → staging обновлён, 6 проверок зелёные | ⬜ |
| T1.3 | Production с approval | T1.2 | Ручной запуск → approval → prod, smoke зелёный | ⬜ |
| T2.1 | Smoke-скрипт и негативные проверки | T1.3 | «Плохой» образ валит smoke с понятным кодом | ⬜ |
| T2.2 | Атомарный откат | T2.1 | Плохой деплой → автоматический rollback, сервис доступен | ⬜ |
| T3.1 | DORA-метрики | T2.2 | Цифры за 30 дней, doc, повторяемый запуск | ⬜ |
| T4.1 | Документация и runbook деплоя/отката | T3.1 | Операция воспроизводится за 10 минут | ⬜ |

### Волны

```
Волна 1: T0.1
Волна 2: T1.1 → T1.2 → T1.3
Волна 3: T2.1 → T2.2
Волна 4: T3.1 → T4.1
```

## 7. Список коммитов

1. `docs: план M10 — непрерывная доставка` (T0.1)
2. `ci: публикация образа сервиса` (T1.1)
3. `ci: деплой в staging` (T1.2)
4. `ci: production-деплой с approval` (T1.3)
5. `test: smoke-проверки сервиса` (T2.1)
6. `feat: атомарный откат` (T2.2)
7. `feat: DORA-метрики` (T3.1)
8. `docs: деплой и откат` (T4.1)

## 8. Чек-лист приёмки

- [ ] Деплой не требует ручных команд на сервере.
- [ ] В логах деплоя нет секретов; kubeconfig не печатается.
- [ ] Откат проверен на настоящем плохом образе, а не только описан.
- [ ] DORA-цифры можно пересчитать одной командой.
- [ ] Staging и prod не перетирают друг друга (namespaces/базы).
- [ ] Failure mode: недоступный кластер → job падает понятно, без «полудеплоя».

## 9. Риски и меры

| Риск | Мера |
|---|---|
| Один кластер на staging/prod | Разные namespaces и БД; ограничение описано; managed-разделение — следующий шаг |
| Секреты в логах Actions | Маскирование, `set +x`, проверка вывода smoke |
| Долгий `--wait` | Таймаут 5 мин, `--atomic`; job timeout 20 мин |
| Дрейф values | Helm values в Git, деплой только из CI; ручные `kubectl edit` запрещены |
| DORA считается неверно | Явные определения в doc; проверка на известных событиях |

## 10. Журнал задач

| Дата | Задача | Результат | Commit |
|---|---|---|---|
| 2026-11-01 | — | План создан; границы с M6 T5.1 зафиксированы | — |

## 11. Вне вехи

- Canary/blue-green через Argo Rollouts, feature flags.
- GitOps (Argo CD/Flux), auto-sync и drift detection.
- Многорегиональность, managed DB, HA control plane.
- Реальный on-call и PagerDuty (учебные учения — M11).



