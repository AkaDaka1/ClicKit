"""Демо наблюдаемости «сломай и почини» (M8 T5.1).

Проверяет весь контур **лог → метрика → алерт → runbook → SLO** на живом
стеке: генерирует трафик, ломает API, дожидается `ClikitApiDown` в Prometheus,
Alertmanager и локальном приёмнике, потом возвращает сервис и ждёт `resolved`.
Сценарий описан для человека в
[`docs/observability-demo.md`](../docs/observability-demo.md);
этот скрипт — его исполняемая версия: ждёт не «на глаз», а по факту алерта, и
возвращает код выхода, поэтому демо воспроизводимо с чистой машины.

Почему скрипт, а не только инструкция:

* «сломай и почини» проверяет не картинки, а состояние: алерт должен
  перейти в `firing`, затем в `resolved` — это можно утверждать, а не
  показывать;
* ожидание по времени (`for: 1m`) меняется при правке правил, поэтому
  таймауты и опрос идут через API, а не через `Start-Sleep 90`;
* в M11 те же шаги станут основой chaos-учений, а в M10 — смоук-проверкой
  доставки: код выхода уже есть.

Что важно честно показать в демо (ADR №70): падение API **не видно в SLI**
(`docs/sre/slo.md` §3) — запросы не доходят до приложения. Поэтому
`ClikitApiDown` считается по `up == 0`, а отчёт по error budget остаётся
`normal`: бюджет жжётся ошибками на дошедших запросах, а не отсутствием
трафика. Демо не притворяется, что контур видит всё.

Примеры:

    python scripts/observability_demo.py check
    python scripts/observability_demo.py run
    python scripts/observability_demo.py run --json
    python scripts/observability_demo.py run --timeout 300

Коды выхода:

    0 — демо пройдено (или стек готов, для `check`);
    1 — шаг не уложился в таймаут или проверка не прошла;
    2 — стек наблюдаемости не поднят / нет `docker` (это не «всё хорошо»).

Скрипт всегда старается вернуть API в строй, даже если демо упало посередине:
оставлять сервис выключенным после демонстрации нельзя.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeVar

ROOT = Path(__file__).resolve().parents[1]
# Запуск как `python scripts/observability_demo.py`: корень репозитория нужен
# для импорта `scripts.slo_report` (отчёт по бюджету — тот же код, что T4.1).
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

#: Compose-файл стека (единственная команда запуска, docs/observability.md §3).
DEFAULT_COMPOSE_FILE = "docker-compose.observability.yml"
#: Адреса по умолчанию: стек публикует порты только на localhost (T2.1).
DEFAULT_PROMETHEUS_URL = "http://127.0.0.1:9090"
DEFAULT_ALERTMANAGER_URL = "http://127.0.0.1:9093"
DEFAULT_SINK_URL = "http://127.0.0.1:8080"
DEFAULT_API_URL = "http://127.0.0.1:8000"

#: Алерт, который проверяет демо: единственный, ловящий полное падение
#: (SLI его не видит — docs/sre/slo.md §3).
ALERT_NAME = "ClikitApiDown"

#: Цели, которые обязаны быть UP до начала демо (`docs/observability.md` §4).
EXPECTED_TARGETS = (
    "alertmanager",
    "clikit-api",
    "grafana",
    "loki",
    "node-exporter",
    "prometheus",
    "promtail",
    "tempo",
)

#: Коды выхода — контракт скрипта, на них опираются тесты и будущие учения M11.
EXIT_OK = 0
EXIT_FAILED = 1
EXIT_NOT_READY = 2

#: Ожидание одного шага: `for: 1m` + скрейп 15 с + оценка правил 15 с + запас.
DEFAULT_TIMEOUT = 240.0
#: Период опроса состояний (Prometheus/Alertmanager/приёмник).
DEFAULT_INTERVAL = 2.0


class DemoError(RuntimeError):
    """Шаг демо не выполнен (таймаут, ответ не тот, команда упала)."""


def http_json(url: str, *, timeout: float = 5.0) -> Any:
    """Прочитать JSON по HTTP.

    Args:
        url: Полный URL запроса.
        timeout: Таймаут в секундах.

    Returns:
        Разобранный JSON-ответ.

    Raises:
        DemoError: Сервис недоступен или ответ не JSON.
    """
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise DemoError(f"{url}: сервис недоступен ({exc})") from exc
    except json.JSONDecodeError as exc:
        raise DemoError(f"{url}: ответ не JSON ({exc})") from exc


def http_status(url: str, *, timeout: float = 5.0) -> int:
    """Код ответа HTTP без разбора тела (проба живости).

    Args:
        url: Полный URL запроса.
        timeout: Таймаут в секундах.

    Returns:
        HTTP-статус ответа.

    Raises:
        DemoError: Сервис недоступен.
    """
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return int(response.status)
    except urllib.error.HTTPError as exc:
        return int(exc.code)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise DemoError(f"{url}: сервис недоступен ({exc})") from exc


def target_health(prometheus_url: str) -> dict[str, str]:
    """Состояние scrape-целей Prometheus.

    Args:
        prometheus_url: Базовый URL Prometheus.

    Returns:
        Словарь `job → health` (`up`, `down`, `unknown`).

    Raises:
        DemoError: Prometheus недоступен или ответ не в формате API.
    """
    payload = http_json(f"{prometheus_url.rstrip('/')}/api/v1/targets")
    data = payload.get("data") if isinstance(payload, dict) else None
    targets = data.get("activeTargets") if isinstance(data, dict) else None
    if not isinstance(targets, list):
        raise DemoError("Prometheus: нет поля data.activeTargets")
    health: dict[str, str] = {}
    for target in targets:
        if not isinstance(target, dict):
            continue
        labels = target.get("labels") or {}
        job = str(labels.get("job") or "")
        if job:
            health[job] = str(target.get("health") or "unknown")
    return health


def missing_targets(health: dict[str, str]) -> list[str]:
    """Цели, которых нет или которые не UP — по контракту `EXPECTED_TARGETS`."""
    return [job for job in EXPECTED_TARGETS if health.get(job) != "up"]


def alert_states(prometheus_url: str, name: str = ALERT_NAME) -> list[str]:
    """Состояния алерта в Prometheus (`pending`/`firing`).

    Args:
        prometheus_url: Базовый URL Prometheus.
        name: Имя алерта.

    Returns:
        Список состояний; пустой список — алерта нет (норма или resolved).
    """
    payload = http_json(f"{prometheus_url.rstrip('/')}/api/v1/alerts")
    data = payload.get("data") if isinstance(payload, dict) else None
    alerts = data.get("alerts") if isinstance(data, dict) else None
    states: list[str] = []
    for alert in alerts if isinstance(alerts, list) else []:
        if not isinstance(alert, dict):
            continue
        labels = alert.get("labels") or {}
        if str(labels.get("alertname") or "") == name:
            states.append(str(alert.get("state") or "unknown"))
    return states


def alertmanager_states(alertmanager_url: str, name: str = ALERT_NAME) -> list[str]:
    """Состояния алерта в Alertmanager (`active`/`suppressed`/…).

    Args:
        alertmanager_url: Базовый URL Alertmanager.
        name: Имя алерта.

    Returns:
        Список состояний из `status.state`.
    """
    payload = http_json(f"{alertmanager_url.rstrip('/')}/api/v2/alerts")
    states: list[str] = []
    for alert in payload if isinstance(payload, list) else []:
        if not isinstance(alert, dict):
            continue
        labels = alert.get("labels") or {}
        if str(labels.get("alertname") or "") != name:
            continue
        status = alert.get("status") or {}
        states.append(str(status.get("state") or "unknown"))
    return states


def sink_payload(sink_url: str) -> dict[str, Any]:
    """Ответ локального приёмника `GET /alerts`.

    Args:
        sink_url: Базовый URL приёмника (`scripts/alert_sink.py`).

    Returns:
        Словарь ответа приёмника (обычно `{"alerts": [...]}`).

    Raises:
        DemoError: Ответ не объект.
    """
    payload = http_json(f"{sink_url.rstrip('/')}/alerts")
    if not isinstance(payload, dict):
        raise DemoError("приёмник: ожидается JSON-объект")
    return payload


def sink_states(sink_url: str, name: str = ALERT_NAME) -> list[str]:
    """Статусы алерта, доставленные в приёмник (`firing`/`resolved`).

    Args:
        sink_url: Базовый URL приёмника.
        name: Имя алерта.

    Returns:
        Список статусов в порядке поступления.
    """
    alerts = sink_payload(sink_url).get("alerts") or []
    states: list[str] = []
    for record in alerts if isinstance(alerts, list) else []:
        if not isinstance(record, dict):
            continue
        if str(record.get("alertname") or "") == name:
            states.append(str(record.get("status") or "unknown"))
    return states


def metric_total(prometheus_url: str, expression: str) -> float:
    """Сумма значений PromQL-запроса (для наглядного счётчика в демо).

    Args:
        prometheus_url: Базовый URL Prometheus.
        expression: PromQL-выражение.

    Returns:
        Сумма значений всех серий; `0.0`, если серий нет.
    """
    query = urllib.parse.urlencode({"query": expression})
    url = f"{prometheus_url.rstrip('/')}/api/v1/query?{query}"
    payload = http_json(url)
    data = payload.get("data") if isinstance(payload, dict) else None
    result = data.get("result") if isinstance(data, dict) else None
    total = 0.0
    for series in result if isinstance(result, list) else []:
        if not isinstance(series, dict):
            continue
        value = series.get("value") or []
        if len(value) != 2:
            continue
        try:
            total += float(value[1])
        except (TypeError, ValueError):
            continue
    return total


def format_duration(seconds: float) -> str:
    """Перевести секунды в «N мин M с» для строки таймлайна."""
    total = int(round(max(seconds, 0.0)))
    minutes, rest = divmod(total, 60)
    if minutes:
        return f"{minutes} мин {rest:02d} с"
    return f"{rest} с"


T = TypeVar("T")


def wait_for(
    probe: Callable[[], T],
    *,
    timeout: float,
    interval: float = DEFAULT_INTERVAL,
    describe: str = "состояние",
) -> tuple[float, T]:
    """Опрашивать `probe`, пока он не вернёт истину.

    Args:
        probe: Функция без аргументов; истинный результат — успех шага.
        timeout: Предельное ожидание в секундах.
        interval: Пауза между опросами в секундах.
        describe: Что ждём — для текста ошибки.

    Returns:
        Пару «сколько ждали, результат».

    Raises:
        DemoError: Таймаут или ошибка пробы (последняя ошибка сохраняется).
    """
    started = time.monotonic()
    last_error: Exception | None = None
    while True:
        elapsed = time.monotonic() - started
        try:
            result = probe()
            last_error = None
        except DemoError as exc:
            result = None  # type: ignore[assignment]
            last_error = exc
        if result:
            return elapsed, result
        if elapsed >= timeout:
            suffix = f" Последняя ошибка: {last_error}" if last_error else ""
            raise DemoError(
                f"за {format_duration(timeout)} не дождались: {describe}.{suffix}"
            )
        time.sleep(interval)


def compose(
    compose_file: Path,
    *arguments: str,
    timeout: float = 120.0,
) -> subprocess.CompletedProcess[str]:
    """Выполнить `docker compose -f <file> <arguments>` из корня репозитория.

    Args:
        compose_file: Путь к compose-файлу стека.
        arguments: Аргументы команды compose (`stop`, `start`, `api`).
        timeout: Таймаут команды в секундах.

    Returns:
        Результат процесса.

    Raises:
        DemoError: `docker` не найден или команда завершилась с ошибкой.
    """
    if shutil.which("docker") is None:
        raise DemoError("docker не найден в PATH: демо требует Docker Desktop")
    command = ["docker", "compose", "-f", str(compose_file), *arguments]
    try:
        completed = subprocess.run(  # noqa: S603 — фиксированный argv без shell
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DemoError(f"команда {' '.join(command)} не выполнена: {exc}") from exc
    if completed.returncode != 0:
        details = (completed.stderr or completed.stdout or "").strip().splitlines()
        tail = details[-1] if details else "без вывода"
        raise DemoError(f"{' '.join(arguments)}: код {completed.returncode} ({tail})")
    return completed


class Timeline:
    """Таймлайн демо: строка на шаг с секундами от начала (как в постмортеме)."""

    def __init__(self, *, echo: Callable[[str], None] = print) -> None:
        """Создать таймлайн.

        Args:
            echo: Куда печатать строки (в тестах — в список).
        """
        self._started = time.monotonic()
        self._echo = echo
        self.events: list[tuple[float, str]] = []

    @property
    def elapsed(self) -> float:
        """Секунды с начала демо."""
        return time.monotonic() - self._started

    def log(self, text: str) -> None:
        """Записать шаг и напечатать его с отметкой времени."""
        elapsed = self.elapsed
        self.events.append((elapsed, text))
        self._echo(f"[{format_duration(elapsed).rjust(9)}] {text}")


@dataclass
class DemoResult:
    """Итог демо: что проверено и сколько это заняло.

    Attributes:
        checks: Пары «проверка → пройдена» в порядке выполнения.
        seconds: Общая длительность демо.
        budget_state: Режим политики error budget после восстановления.
        events: Таймлайн (секунды от начала, текст).
        error: Причина провала, если демо не завершилось.
        not_ready: Стек не готов к демо (это не провал проверки, а условие).
    """

    checks: list[tuple[str, bool]] = field(default_factory=list)
    seconds: float = 0.0
    budget_state: str | None = None
    events: list[tuple[float, str]] = field(default_factory=list)
    error: str | None = None
    not_ready: bool = False
    _passed: bool = True

    @property
    def exit_code(self) -> int:
        """Код выхода: 0 — все проверки пройдены, 1 — нет."""
        if self.error or not self._passed or any(not ok for _, ok in self.checks):
            return EXIT_FAILED
        return EXIT_OK

    def check(self, name: str, passed: bool = True) -> None:
        """Записать результат проверки."""
        self.checks.append((name, passed))
        if not passed:
            self._passed = False

    def as_dict(self) -> dict[str, Any]:
        """Представить итог как словарь для `--json`."""
        return {
            "checks": [{"name": name, "passed": ok} for name, ok in self.checks],
            "passed": self.exit_code == EXIT_OK,
            "not_ready": self.not_ready,
            "seconds": round(self.seconds, 1),
            "budget_state": self.budget_state,
            "error": self.error,
            "events": [
                {"seconds": round(seconds, 1), "text": text}
                for seconds, text in self.events
            ],
            "exit_code": self.exit_code,
        }


@dataclass(frozen=True)
class DemoOptions:
    """Параметры демо: адреса, compose-файл и таймауты.

    Attributes:
        prometheus_url: Базовый URL Prometheus.
        alertmanager_url: Базовый URL Alertmanager.
        sink_url: Базовый URL локального приёмника алертов.
        api_url: Базовый URL ClicKit Cloud.
        compose_file: Compose-файл стека наблюдаемости.
        timeout: Ожидание одного шага в секундах.
        interval: Период опроса состояний в секундах.
    """

    prometheus_url: str = DEFAULT_PROMETHEUS_URL
    alertmanager_url: str = DEFAULT_ALERTMANAGER_URL
    sink_url: str = DEFAULT_SINK_URL
    api_url: str = DEFAULT_API_URL
    compose_file: Path = ROOT / DEFAULT_COMPOSE_FILE
    timeout: float = DEFAULT_TIMEOUT
    interval: float = DEFAULT_INTERVAL


def check_stack(options: DemoOptions, timeline: Timeline) -> None:
    """Проверить, что стек поднят: compose читается, все цели UP, API отвечает.

    Raises:
        DemoError: Compose не читается (нет `.env`), цель не UP или API молчит.
    """
    try:
        compose(options.compose_file, "config", "--quiet")
    except DemoError as exc:
        raise DemoError(
            f"compose-файл не читается: {exc}. Нужен `.env` с CLICKIT_API_KEY и "
            "POSTGRES_PASSWORD (docs/observability.md §3: Copy-Item .env.example .env)"
        ) from exc
    try:
        health = target_health(options.prometheus_url)
    except DemoError as exc:
        raise DemoError(
            f"стек наблюдаемости не поднят: {exc}. Запуск: docker compose -f "
            f"{DEFAULT_COMPOSE_FILE} up -d --build"
        ) from exc
    broken = missing_targets(health)
    if broken:
        raise DemoError(
            "не UP targets: "
            + ", ".join(broken)
            + ". Проверьте docs/observability.md §4 и §7"
        )
    timeline.log(
        f"стек готов: {len(EXPECTED_TARGETS)}/{len(EXPECTED_TARGETS)} targets UP"
    )
    try:
        status = http_status(f"{options.api_url.rstrip('/')}/healthz")
    except DemoError as exc:
        raise DemoError(f"API не отвечает: {exc}") from exc
    if status != 200:
        raise DemoError(f"GET /healthz вернул {status}, ожидался 200")
    timeline.log("API отвечает: GET /healthz → 200")


def make_traffic(options: DemoOptions, timeline: Timeline) -> None:
    """Сгенерировать запрос к пользовательскому маршруту (метрика, лог, трейс).

    Список сценариев — публичный GET без ключа: демо не просит секретов из
    `.env`, а метрика, JSON-лог и спан всё равно появляются.

    Raises:
        DemoError: Ответ не 2xx.
    """
    url = f"{options.api_url.rstrip('/')}/v1/scenarios?limit=1"
    status = http_status(url)
    if not 200 <= status < 300:
        raise DemoError(f"GET /v1/scenarios вернул {status}, ожидался 200")
    total = metric_total(options.prometheus_url, "sum(clikit_http_requests_total)")
    timeline.log(
        f"трафик: GET /v1/scenarios → {status}; "
        f"clikit_http_requests_total = {total:.0f}"
    )


def break_api(options: DemoOptions, timeline: Timeline) -> None:
    """Сломать сервис: остановить контейнер `api` (обратимое действие).

    Raises:
        DemoError: Команда compose не выполнена.
    """
    compose(options.compose_file, "stop", "api")
    timeline.log("сломали: docker compose stop api")


def restore_api(options: DemoOptions, timeline: Timeline) -> None:
    """Вернуть сервис в строй.

    Raises:
        DemoError: Команда compose не выполнена.
    """
    compose(options.compose_file, "start", "api")
    timeline.log("чиним: docker compose start api")


def watch_firing(options: DemoOptions, timeline: Timeline, result: DemoResult) -> None:
    """Дождаться `ClikitApiDown` во всех трёх местах: Prometheus → AM → приёмник.

    Raises:
        DemoError: Шаг не уложился в таймаут.
    """
    pending_seen = {"value": False}

    def _firing() -> bool:
        states = alert_states(options.prometheus_url)
        if "pending" in states and not pending_seen["value"]:
            pending_seen["value"] = True
            timeline.log("Prometheus: ClikitApiDown pending")
        return "firing" in states

    waited, _ = wait_for(
        _firing,
        timeout=options.timeout,
        interval=options.interval,
        describe=f"{ALERT_NAME} в состоянии firing (Prometheus)",
    )
    timeline.log(
        f"Prometheus: {ALERT_NAME} firing через {format_duration(waited)} "
        "(for: 1m + скрейп + оценка правил)"
    )
    result.check("Prometheus: алерт перешёл в firing")

    waited, _ = wait_for(
        lambda: alertmanager_states(options.alertmanager_url),
        timeout=options.timeout,
        interval=options.interval,
        describe=f"{ALERT_NAME} в Alertmanager",
    )
    timeline.log(f"Alertmanager: алерт принят через {format_duration(waited)}")
    result.check("Alertmanager: алерт принят")

    waited, states = wait_for(
        lambda: [state for state in sink_states(options.sink_url) if state == "firing"],
        timeout=options.timeout,
        interval=options.interval,
        describe=f"доставку {ALERT_NAME} (firing) в приёмник",
    )
    timeline.log(
        f"приёмник: [firing] {ALERT_NAME} через {format_duration(waited)} "
        f"(записей: {len(states)})"
    )
    result.check("приёмник: получил firing")


def watch_resolved(
    options: DemoOptions, timeline: Timeline, result: DemoResult
) -> None:
    """Дождаться восстановления: API жив, алерт исчез, приёмник получил resolved.

    Raises:
        DemoError: Шаг не уложился в таймаут.
    """
    waited, _ = wait_for(
        lambda: http_status(f"{options.api_url.rstrip('/')}/healthz") == 200,
        timeout=options.timeout,
        interval=options.interval,
        describe="GET /healthz → 200 после старта API",
    )
    timeline.log(f"API снова отвечает через {format_duration(waited)}")
    result.check("API: восстановлен")

    waited, _ = wait_for(
        lambda: not alert_states(options.prometheus_url),
        timeout=options.timeout,
        interval=options.interval,
        describe=f"исчезновение {ALERT_NAME} из Prometheus",
    )
    timeline.log(f"Prometheus: алерт исчез через {format_duration(waited)}")
    result.check("Prometheus: алерт снят")

    waited, _ = wait_for(
        lambda: not alertmanager_states(options.alertmanager_url),
        timeout=options.timeout,
        interval=options.interval,
        describe=f"исчезновение {ALERT_NAME} из Alertmanager",
    )
    timeline.log(f"Alertmanager: алерт снят через {format_duration(waited)}")
    result.check("Alertmanager: алерт снят")

    waited, records = wait_for(
        lambda: [
            state for state in sink_states(options.sink_url) if state == "resolved"
        ],
        timeout=options.timeout,
        interval=options.interval,
        describe=f"доставку {ALERT_NAME} (resolved) в приёмник",
    )
    timeline.log(
        f"приёмник: [resolved] {ALERT_NAME} через {format_duration(waited)} "
        f"(записей: {len(records)})"
    )
    result.check("приёмник: получил resolved")


def report_budget(options: DemoOptions, timeline: Timeline, result: DemoResult) -> None:
    """Показать error budget после восстановления (T4.1) — контур замкнут.

    Отчёт читается тем же кодом, что и `scripts/slo_report.py`: копия формулы
    в демо была бы дефектом (ADR №68).
    """
    try:
        from scripts.slo_report import collect_report
    except ImportError:  # pragma: no cover — запуск из нестандартного каталога
        sys.path.insert(0, str(ROOT))
        from scripts.slo_report import collect_report

    try:
        report = collect_report(options.prometheus_url)
    except (OSError, ValueError) as exc:
        timeline.log(f"error budget: нет данных ({exc})")
        result.budget_state = None
        return
    result.budget_state = report.state
    minutes = (
        "нет данных"
        if report.remaining_minutes is None
        else f"{report.remaining_minutes:.1f} мин"
    )
    timeline.log(
        f"error budget: режим {report.state}, остаток {minutes} "
        "(падение API не видно в SLI — docs/sre/slo.md §3)"
    )
    result.check(f"error budget: режим {report.state}", report.state == "normal")


def run_demo(options: DemoOptions, *, timeline: Timeline | None = None) -> DemoResult:
    """Выполнить демо целиком.

    Args:
        options: Адреса, compose-файл и таймауты.
        timeline: Таймлайн (по умолчанию — печать в stdout).

    Returns:
        Итог демо; исключения шагов записаны в `error`, а не выброшены.
    """
    timeline = timeline or Timeline()
    result = DemoResult()
    started = time.monotonic()
    broken = False
    try:
        check_stack(options, timeline)
    except DemoError as exc:
        result.error = str(exc)
        result.not_ready = True
        timeline.log(f"стек не готов: {exc}")
        result.seconds = time.monotonic() - started
        result.events = list(timeline.events)
        return result
    try:
        make_traffic(options, timeline)
        break_api(options, timeline)
        broken = True
        watch_firing(options, timeline, result)
        restore_api(options, timeline)
        broken = False
        watch_resolved(options, timeline, result)
        report_budget(options, timeline, result)
    except DemoError as exc:
        result.error = str(exc)
        timeline.log(f"провал: {exc}")
    finally:
        if broken:
            # Демо упало между поломкой и починкой: сервис нельзя оставлять
            # выключенным (docs/sre/runbook.md §1.2 — «восстановление важнее»).
            try:
                compose(options.compose_file, "start", "api")
                timeline.log("аварийное восстановление: docker compose start api")
            except DemoError as exc:
                timeline.log(f"аварийное восстановление не удалось: {exc}")
        result.seconds = time.monotonic() - started
        result.events = list(timeline.events)
    return result


def format_result(result: DemoResult) -> str:
    """Собрать итоговую сводку демо для терминала."""
    lines = ["", "Проверки демо:"]
    for name, passed in result.checks:
        lines.append(f"  {'OK  ' if passed else 'FAIL'} {name}")
    if result.not_ready:
        lines.append("")
        lines.append("ДЕМО НЕ ЗАПУЩЕНО: стек наблюдаемости не готов.")
        lines.append(f"Причина: {result.error}")
        return "\n".join(lines)
    verdict = "ДЕМО ПРОЙДЕНО" if result.exit_code == EXIT_OK else "ДЕМО НЕ ПРОЙДЕНО"
    lines.append("")
    lines.append(f"{verdict} за {format_duration(result.seconds)}.")
    if result.error:
        lines.append(f"Причина: {result.error}")
    lines.append(
        "Действия при провале: runbook.md §3, сценарий — docs/observability-demo.md."
    )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    """Собрать парсер аргументов."""
    parser = argparse.ArgumentParser(
        description="Демо наблюдаемости «сломай и почини» (M8 T5.1).",
    )
    parser.add_argument(
        "command",
        choices=("run", "check"),
        nargs="?",
        default="run",
        help="run — полный сценарий, check — только готовность стека",
    )
    parser.add_argument(
        "--prometheus-url",
        default=DEFAULT_PROMETHEUS_URL,
        help=f"базовый URL Prometheus (по умолчанию {DEFAULT_PROMETHEUS_URL})",
    )
    parser.add_argument(
        "--alertmanager-url",
        default=DEFAULT_ALERTMANAGER_URL,
        help=f"базовый URL Alertmanager (по умолчанию {DEFAULT_ALERTMANAGER_URL})",
    )
    parser.add_argument(
        "--sink-url",
        default=DEFAULT_SINK_URL,
        help=f"базовый URL приёмника алертов (по умолчанию {DEFAULT_SINK_URL})",
    )
    parser.add_argument(
        "--api-url",
        default=DEFAULT_API_URL,
        help=f"базовый URL API (по умолчанию {DEFAULT_API_URL})",
    )
    parser.add_argument(
        "--compose-file",
        default=str(ROOT / DEFAULT_COMPOSE_FILE),
        help=f"compose-файл стека (по умолчанию {DEFAULT_COMPOSE_FILE})",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help=f"ожидание одного шага в секундах (по умолчанию {DEFAULT_TIMEOUT:.0f})",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="печатать машинночитаемый итог вместо сводки",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Точка входа: `check` или полный сценарий `run`.

    Args:
        argv: Аргументы командной строки (по умолчанию `sys.argv[1:]`).

    Returns:
        Код выхода 0/1/2 (см. docstring модуля).
    """
    args = build_parser().parse_args(argv)
    options = DemoOptions(
        prometheus_url=args.prometheus_url,
        alertmanager_url=args.alertmanager_url,
        sink_url=args.sink_url,
        api_url=args.api_url,
        compose_file=Path(args.compose_file),
        timeout=args.timeout,
    )
    if not options.compose_file.exists():
        print(f"нет compose-файла: {options.compose_file}", file=sys.stderr)
        return EXIT_NOT_READY

    if args.command == "check":
        timeline = Timeline()
        try:
            check_stack(options, timeline)
        except DemoError as exc:
            print(f"Стек не готов: {exc}", file=sys.stderr)
            return EXIT_NOT_READY
        print("Стек готов к демо. Запуск: python scripts/observability_demo.py run")
        return EXIT_OK

    timeline = Timeline()
    result = run_demo(options, timeline=timeline)
    if args.json:
        print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2))
    else:
        print(format_result(result))
    if result.not_ready:
        return EXIT_NOT_READY
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
