# Contributing to ClicKit · Участие в ClicKit

> **English summary.** Contributions are welcome. Open an issue first for
> non-trivial changes, keep one feature per pull request, run
> `ruff check . && ruff format --check . && python -m pytest`, and update the
> project documents (`AI_CONTEXT.md`, `PROGRESS.md`) together with the code.
> By participating you agree to the [Code of Conduct](CODE_OF_CONDUCT.md).
> Security issues must be reported privately — see [SECURITY.md](SECURITY.md).

Спасибо за интерес к ClicKit! Проект небольшой, поэтому правила простые:
одна задача — один понятный коммит/PR, зелёные проверки и актуальная
документация.

## С чего начать

- **Баг или идея.** Откройте issue по шаблону: для ошибок приложите версию,
  версию Windows, способ запуска (архив или `python -m app`) и фрагмент
  журнала из `%APPDATA%\ClicKit\logs\app.log`.
- **Крупное изменение.** Сначала обсудите его в issue: архитектура и планы
  вех зафиксированы в [`AI_CONTEXT.md`](AI_CONTEXT.md) и [`plans/`](plans/README.md),
  и менять их «по ходу PR» не принято.
- **Задача из плана вехи.** Возьмите задачу по ID (например, `T4.2`) и
  убедитесь, что все её зависимости закрыты; работайте по разделу плана
  `plans/M<#>-*.md` и по его чек-листу приёмки.

## Настройка окружения

```bash
git clone https://github.com/AkaDaka1/ClicKit.git
cd ClicKit
python -m venv .venv
.venv\Scripts\activate           # PowerShell: .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m app
```

Для релизной сборки — `pip install -r requirements-build.txt`.
Для ClicKit Cloud — `pip install -r requirements-service.txt` (и
`requirements-service-test.txt` для тестов), инструкции в
[`docs/api.md`](docs/api.md).

## Обязательные проверки перед PR

```bash
ruff check .
ruff format --check .
python -m pytest
```

Те же команды выполняет CI (`.github/workflows/ci.yml`) на Windows
(Python 3.11–3.13) и Linux-контейнер (`docker compose run --rm test`).
На PR должны быть зелёными все job'ы: `lint`, `tests`, `tests-docker`.

Если менялся интерфейс, приложите скриншот. Снимки для README
пересобираются одной командой (offscreen-рендер, мышь не двигается):

```bash
python scripts/make_screenshots.py
```

## Правила кода

- **Python 3.11+, type hints везде.** Идентификаторы — на английском,
  комментарии и документация — на русском (так уже написан весь проект).
- **Линтер — ruff** (`pyproject.toml`): `E`, `F`, `W`, `I`, `UP`, `B`,
  длина строки 88. Форматирование — `ruff format`.
- **Слоистость.** `core/` не импортирует `gui/` и PySide6; GUI не знает
  подробностей эмуляции ввода. Сценарии исполняются только в фоновом потоке,
  главный поток Qt не блокируется.
- **Сценарий — данные.** Не исполняйте произвольный код из Blockly: любой
  сценарий проходит через IR и валидацию `core/ir/schema.py`.
- **Тесты.** Новое поведение — с автотестом; баг — сначала воспроизводящий
  тест. Тесты сервиса лежат в `tests/service/` и запускаются отдельно:
  `python -m pytest tests/service`.

## Ветки и коммиты

- Ветка от актуального `master`: `feat/<кратко>`, `fix/<кратко>`,
  `docs/<кратко>`, `refactor/<кратко>`, `test/<кратко>`, `chore/<кратко>`.
- Формат сообщения: `type: subject` (`feat`, `fix`, `docs`, `refactor`,
  `test`, `chore`), тема — короткая и конкретная.
- **Одна фича = один коммит.** Не смешивайте рефакторинг, переименования и
  поведенческие изменения в одном коммите без необходимости.
- Пуш в `master` — только через pull request с зелёным CI.

## Документация — часть изменения

Проект ведёт единый источник правды, и он должен оставаться правдой:

| Изменение | Что обновить |
|---|---|
| Архитектура, зависимости, новый каталог, значимое решение | `AI_CONTEXT.md` (§3.2 структура, §3.3 ADR) |
| Выполненная задача вехи | план `plans/M<#>-*.md` (статус, журнал) и `PROGRESS.md` |
| Новая фича или изменение запуска/установки | `README.md` (EN и RU) |
| Новые артефакты сборки, кэши, локальные данные | `.gitignore` |

## Pull request

В описании PR укажите:

- [ ] что и зачем изменено (и на какой issue/задачу плана ссылается);
- [ ] как проверено (`ruff`, `pytest`, ручной сценарий — что именно нажимали);
- [ ] обновлена ли документация по таблице выше;
- [ ] для изменений интерфейса — скриншот до/после.

Ревью смотрит на слоистость, отсутствие побочных эффектов в GUI-потоке,
понятность ошибок для пользователя и покрытие тестами. Спасибо!
