# M9 — Инфраструктура как код

> План создан 2026-11-01. Статус: 📋 запланировано.
> Зависимости: M7 (образ сервиса, health-эндпоинты), M6 T3.2 (публикация
> образов в GHCR). M9 не переделывает M6: тестовый и сборочный образы
> остаются там, здесь появляется облачная инфраструктура сервиса.

## 1. Цель

Убрать «ручные клики» из эксплуатации: описать облако, кластер и приложение
кодом, чтобы окружение можно было создать с нуля, проверить в PR и удалить
одной командой. Получить публичный HTTPS-адрес сервиса как доказательство
работоспособности.

## 2. Критерий готовности

- [ ] `terraform fmt -check`, `terraform validate`, `tflint` и `trivy config`
      проходят без ошибок.
- [ ] `terraform apply` с нуля создаёт сеть, подсеть, security groups, VM,
      статический IP и DNS-запись; outputs содержат IP и FQDN.
- [ ] cloud-init/Ansible ставит k3s, ingress-nginx и cert-manager; узел Ready,
      ClusterIssuer Ready.
- [ ] `helm install` разворачивает сервис; `kubectl rollout status` успешен;
      `https://<домен>/healthz` → 200 с валидным сертификатом, HTTP → HTTPS.
- [ ] В чарте заданы probes, requests/limits, HPA, PDB, NetworkPolicy,
      `securityContext` (non-root, read-only rootfs, drop ALL).
- [ ] `helm lint` и `helm template` проверяются в CI; `terraform plan`
      выполняется на PR (или вручную при отсутствии облачных кредов).
- [ ] `terraform destroy` удаляет ресурсы; повторный `apply` снова поднимает
      окружение (проверка воспроизводимости).
- [ ] `docs/infra.md`: схема, порядок bootstrap, стоимость, ограничения
      single-node k3s и что нужно для production-HA.

## 3. Согласованные параметры

| Параметр | Решение |
|---|---|
| Облако | Выбрать в T0.1: Yandex Cloud (ближе к Т-Банку), Selectel или Timeweb; бюджет ≤ $15/мес |
| Terraform | Terraform ≥ 1.7 (совместим с OpenTofu); модули `network`, `compute`, `dns` |
| State | S3-совместимый bucket с версионированием; lock — по возможности; локальный state только для спайка |
| Кластер | k3s single-node на Ubuntu 24.04 LTS, 2 vCPU / 4 ГБ / 40 ГБ |
| Ingress | ingress-nginx; TLS — cert-manager + Let's Encrypt (staging → prod) |
| Приложение | Helm-чарт `deploy/helm/clikit-cloud`; values `staging`/`prod` |
| Доступ | SSH только с admin-IP; 80/443 — публично; 6443 — только admin-IP |
| Секреты | Не в Terraform/Helm values; GitHub Environments и k8s Secret |
| Резервный путь | Если облако недоступно — k3d локально + Terraform-провайдер Kubernetes; публичный URL тогда откладывается |

## 4. Модули и интерфейсы

```
infra/
├── terraform/
│   ├── modules/network/    # VPC, подсеть, security groups
│   ├── modules/compute/    # VM, диск, статический IP, SSH-ключ
│   ├── modules/dns/        # A-запись
│   └── envs/dev/           # backend, переменные, outputs
├── cloud-init/k3s.yaml     # установка k3s, helm, kubectl
└── ansible/playbook.yml    # идемпотентная доводка (опционально)
deploy/helm/clikit-cloud/
├── Chart.yaml
├── values.yaml
├── values-staging.yaml
├── values-prod.yaml
└── templates/{deployment,service,ingress,hpa,pdb,networkpolicy,secret,configmap}.yaml
docs/infra.md
```

### 4.1. Terraform

- `network`: VPC, подсеть, SG: 22 с admin-IP, 80/443 всем, 6443 с admin-IP,
  egress без ограничений.
- `compute`: Ubuntu 24.04, 2 vCPU/4 ГБ/40 ГБ, статический IP, cloud-init,
  SSH-ключ из переменной (не коммитится).
- `dns`: A-запись на статический IP, TTL 300.
- `envs/dev`: backend S3, `terraform.tfvars.example` без секретов.
- Outputs: `public_ip`, `fqdn`, `ssh_user`.

### 4.2. Кластер

- k3s с `--disable traefik` (используем ingress-nginx), kubeconfig с правами
  600, доступ к API только с admin-IP.
- ingress-nginx через Helm; cert-manager + ClusterIssuer Let's Encrypt.
- Namespace `clikit`; позже M10 добавит `clikit-staging`/`clikit-prod`.

### 4.3. Helm-чарт

- Deployment: 1–2 реплики, `readinessProbe` `/readyz`, `livenessProbe`
  `/healthz`, `startupProbe`, resources requests/limits.
- Service ClusterIP; Ingress host + TLS secret; HPA CPU 70%, 1–4 реплики;
  PDB `minAvailable: 1`; NetworkPolicy: ingress только от ingress-nginx,
  egress к Postgres/DNS.
- `securityContext`: `runAsNonRoot`, `readOnlyRootFilesystem`, `drop: [ALL]`,
  `allowPrivilegeEscalation: false`.
- Секреты: `DB_URL`, `CLIKIT_API_KEY` — из k8s Secret, созданного вне Git.

## 5. Решения (ADR; итог — в `AI_CONTEXT.md` §3.3)

- **ADR №42 — инфраструктура только кодом.** Ручные изменения в облаке
  запрещены; любое изменение проходит через Terraform plan/apply. Это даёт
  воспроизводимость и возможность удалить окружение без «сирот».
- **ADR №43 — single-node k3s для демо, с честными ограничениями.**
  Дешёвый кластер достаточен для стажировки и демонстрации; HA, managed DB
  и multi-AZ описаны в `docs/infra.md` как следующий шаг, а не выдаются за
  production.
- **ADR №44 — TLS через cert-manager/Let's Encrypt.** HTTPS не «на словах»:
  сертификат выпускается автоматически, HTTP редиректит на HTTPS.

## 6. Граф задач

| ID | Задача | Зависимости | Чекпоинт (done = …) | Статус |
|---|---|---|---|---|
| T0.1 | Выбор облака, домена, бюджета; backend state; скелет Terraform | M7 | `terraform init` работает; решение и стоимость записаны | ⬜ |
| T1.1 | Модуль network: VPC, подсеть, security groups | T0.1 | `plan`/`apply` создаёт сеть; порты ограничены | ⬜ |
| T1.2 | Модуль compute: VM, диск, статический IP, SSH | T1.1 | SSH на VM работает, cloud-init завершён | ⬜ |
| T1.3 | DNS A-запись | T1.2 | `nslookup <домен>` возвращает статический IP | ⬜ |
| T2.1 | k3s + ingress-nginx + cert-manager | T1.3 | Узел Ready, ingress class есть, ClusterIssuer Ready | ⬜ |
| T2.2 | Helm-чарт и локальная проверка на k3d | T2.1 | `helm install` → pods Ready, probes зелёные | ⬜ |
| T3.1 | Деплой в облако и HTTPS | T2.2, M6 T3.2 | `https://<домен>/healthz` 200, HTTP → HTTPS, сертификат валиден | ⬜ |
| T3.2 | Hardening: non-root, NetworkPolicy, PDB, HPA, resources | T3.1 | `kubectl describe` подтверждает настройки; HPA масштабирует | ⬜ |
| T4.1 | Terraform/Helm проверки в CI | T3.2 | fmt/validate/tflint/trivy/plan и `helm lint` зелёные | ⬜ |
| T5.1 | Документация, стоимость, destroy/recreate | T4.1 | `destroy` → `apply` воспроизводит окружение; cost-таблица | ⬜ |

### Волны

```
Волна 1: T0.1
Волна 2: T1.1 → T1.2 → T1.3
Волна 3: T2.1 → T2.2
Волна 4: T3.1 → T3.2
Волна 5: T4.1 → T5.1
```

## 7. Список коммитов

1. `docs: план M9 — инфраструктура как код` (T0.1)
2. `feat: terraform-сеть` (T1.1)
3. `feat: terraform-VM и доступ` (T1.2)
4. `feat: DNS для сервиса` (T1.3)
5. `feat: k3s, ingress и cert-manager` (T2.1)
6. `feat: helm-чарт ClicKit Cloud` (T2.2)
7. `feat: деплой в облако с HTTPS` (T3.1)
8. `feat: hardening кластера` (T3.2)
9. `ci: проверки terraform и helm` (T4.1)
10. `docs: инфраструктура, стоимость и ограничения` (T5.1)

## 8. Чек-лист приёмки

- [ ] Новый человек (или чистая машина) поднимает окружение по `docs/infra.md`
      без устных подсказок.
- [ ] В репозитории нет секретов, SSH-ключей и `terraform.tfstate`.
- [ ] Публичный HTTPS-URL работает; сертификат не самоподписанный.
- [ ] `terraform destroy` не оставляет платных ресурсов.
- [ ] Ограничения single-node k3s и путь к HA описаны явно.
- [ ] Стоимость посчитана и не превышает согласованный бюджет.

## 9. Риски и меры

| Риск | Мера |
|---|---|
| Облачный бюджет | Лимит $15/мес, статический IP и VM — главные статьи; destroy после демо |
| Долгий cold-start k3s | cloud-init с логами, таймаут 15 мин, повторный apply идемпотентен |
| Let's Encrypt rate limit | Сначала staging-issuer, затем production; DNS должен резолвиться до выпуска |
| Windows-контейнеры Docker Desktop | M9 работает с Linux-контейнерами; перед командами проверять `docker context` |
| Секреты в state | State в закрытом bucket, шифрование, `.tfstate` в `.gitignore` |

## 10. Журнал задач

| Дата | Задача | Результат | Commit |
|---|---|---|---|
| 2026-11-01 | — | План создан; облако/бюджет/ограничения зафиксированы | — |

## 11. Вне вехи

- Managed Kubernetes (Yandex Managed k8s), multi-AZ, HA control plane.
- Managed PostgreSQL, реплики, PITR (частично M11 — бэкапы).
- Service mesh, GitOps (Argo CD/Flux), multi-environment кластеры.
- CD-автоматизация — M10; сканирование и chaos — M11.



