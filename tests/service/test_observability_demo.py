"""Проверки демо «сломай и почини» (M8 T5.1).

Демо — приёмка вехи, поэтому проверяются две вещи:

* **связь с контрактом:** имена алерта и целей, адреса, таймаут и сценарий в
  документе не должны разъезжаться с `alerts.yml`, `prometheus.yml` и
  `docs/observability.md` — иначе демо «зелёное» само по себе;
* **поведение скрипта:** разбор ответов Prometheus/Alertmanager/приёмника,
  ожидание состояния, коды выхода и аварийное восстановление. Сеть подменяется
  крошечным HTTP-сервером, Docker не требуется.

Живой чекпоинт (`8/8 targets UP`, `firing` → `resolved` за ~2 минуты) выполнялся
руками и записан в журнале `plans/M8-observability.md`; здесь — дешёвые
инварианты для CI.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from types import TracebackType
from typing import Any

import pytest
import yaml

from scripts import observability_demo as demo
from scripts.observability_demo import (
    ALERT_NAME,
    DEFAULT_COMPOSE_FILE,
    DEFAULT_TIMEOUT,
    EXIT_FAILED,
    EXIT_NOT_READY,
    EXIT_OK,
    EXPECTED_TARGETS,
    DemoError,
    DemoOptions,
    DemoResult,
    Timeline,
    alert_states,
    alertmanager_states,
    format_duration,
    format_result,
    metric_total,
    missing_targets,
    run_demo,
    sink_states,
    target_health,
    wait_for,
)

ROOT = Path(__file__).resolve().parents[2]
DEMO_DOC = ROOT / "docs" / "observability-demo.md"
OBS_DOC = ROOT / "docs" / "observability.md"
RUNBOOK = ROOT / "docs" / "sre" / "runbook.md"
README = ROOT / "README.md"
ALERTS = ROOT / "observability" / "prometheus" / "alerts.yml"
PROMETHEUS = ROOT / "observability" / "prometheus" / "prometheus.yml"
COMPOSE = ROOT / "docker-compose.observability.yml"
SCRIPT = ROOT / "scripts" / "observability_demo.py"

#: Ответы фальшивых сервисов; каждый тест может их переопределить.
TARGETS_UP: dict[str, Any] = {
    "status": "success",
    "data": {
        "activeTargets": [
            {"labels": {"job": job}, "health": "up"} for job in EXPECTED_TARGETS
        ]
    },
}


def _text(path: Path) -> str:
    """Прочитать файл репозитория в UTF-8."""
    return path.read_text(encoding="utf-8")


class _Handler(BaseHTTPRequestHandler):
    """Ответы по путям из словаря `routes` сервера."""

    def do_GET(self) -> None:  # noqa: N802 — имя метода задано stdlib
        routes: dict[str, Any] = getattr(self.server, "routes", {})
        path = self.path.split("?", 1)[0]
        body = routes.get(path, {"status": "success", "data": {}})
        payload = json.dumps(body).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args: Any) -> None:
        """Заглушить журнал HTTP-сервера в тестах."""


class FakeServices:
    """Поддельные Prometheus/Alertmanager/приёмник на свободном порту."""

    def __init__(self, routes: dict[str, Any] | None = None) -> None:
        self.server = HTTPServer(("127.0.0.1", 0), _Handler)
        self.server.routes = routes if routes is not None else {}  # type: ignore[attr-defined]
        self.host, self.port = self.server.server_address
        self._thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        """Базовый URL поддельного сервера."""
        return f"http://{self.host}:{self.port}"

    def routes(self, value: dict[str, Any]) -> None:
        """Заменить набор ответов (состояние можно менять между опросами)."""
        self.server.routes = value  # type: ignore[attr-defined]

    def __enter__(self) -> FakeServices:
        self._thread.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.server.shutdown()
        self.server.server_close()
        self._thread.join(timeout=5)


# --- связь с контрактом --------------------------------------------------------


def test_default_compose_file_exists() -> None:
    """Демо указывает на реальный compose-файл стека, а не на копию."""
    assert (ROOT / DEFAULT_COMPOSE_FILE).exists()
    assert Path(DEFAULT_COMPOSE_FILE).name == "docker-compose.observability.yml"


def test_expected_targets_match_prometheus_scrape_jobs() -> None:
    """Список целей демо совпадает со scrape-конфигом (8 целей, §4 docs)."""
    config = yaml.safe_load(_text(PROMETHEUS))
    jobs = {job["job_name"] for job in config["scrape_configs"]}
    assert set(EXPECTED_TARGETS) == jobs
    assert len(EXPECTED_TARGETS) == 8
    assert "clikit-api" in jobs


def test_alert_name_and_for_match_rules() -> None:
    """Демо ждёт алерт, который действительно существует, и знает его `for`."""
    data = yaml.safe_load(_text(ALERTS))
    rules = {rule["alert"]: rule for group in data["groups"] for rule in group["rules"]}
    assert ALERT_NAME == "ClikitApiDown"
    rule = rules[ALERT_NAME]
    assert rule["for"] == "1m"
    assert rule["labels"]["severity"] == "critical"
    assert 'up{job="clikit-api"} == 0' in rule["expr"]
    # Таймаут шага обязан быть больше `for` + скрейп + оценка правил.
    assert DEFAULT_TIMEOUT >= 180


def test_alertmanager_sends_resolved_and_inhibits_consequences() -> None:
    """Демо рассчитывает на `resolved`; подавление следствий не мешает алерту."""
    config = yaml.safe_load(
        _text(ROOT / "observability" / "alertmanager" / "alertmanager.yml")
    )
    webhook = config["receivers"][0]["webhook_configs"][0]
    assert webhook["send_resolved"] is True
    assert webhook["url"] == "http://alert-sink:8080/webhook"
    inhibited = " ".join(
        str(matcher)
        for rule in config["inhibit_rules"]
        for matcher in rule["target_matchers"]
    )
    assert "ClikitApiDown" not in inhibited.split("alertname=~")[-1].split("|")[0]


def test_demo_document_covers_the_scenario() -> None:
    """Документ описывает полный контур и честно говорит о слепоте SLI."""
    text = _text(DEMO_DOC)
    for heading in (
        "## 1. Что доказывает демо",
        "## 3. Ручной сценарий на 5 минут",
        "## 4. Автоматическая версия",
        "## 5. Чего демо не показывает",
        "## 6. Если что-то пошло не так",
    ):
        assert heading in text, f"нет раздела {heading}"
    for command in (
        "docker compose -f docker-compose.observability.yml stop api",
        "docker compose -f docker-compose.observability.yml start api",
        "python scripts/observability_demo.py check",
        "python scripts/observability_demo.py run",
        "python scripts/slo_report.py",
    ):
        assert command in text, f"нет команды {command}"
    # Честность про SLI: простоя не видно в error budget (slo.md §3).
    assert "не видно в SLI" in text
    assert "slo.md" in text and "runbook.md" in text
    assert "1 мин 48 с" in text, "нет реального замера прогона"


def test_demo_is_linked_from_entry_documents() -> None:
    """Попасть в демо можно из README, документа стека и runbook."""
    assert "observability-demo.md" in _text(README)
    assert "observability-demo.md" in _text(OBS_DOC)
    assert "observability_demo.py" in _text(RUNBOOK)
    assert "observability-demo.md" in _text(RUNBOOK)


def test_demo_document_has_no_secrets() -> None:
    """В сценарии нет ключей и паролей — только имена переменных."""
    text = _text(DEMO_DOC)
    for marker in ("CLICKIT_API_KEY=", "POSTGRES_PASSWORD=", "X-API-Key:"):
        assert marker not in text, f"похоже на секрет: {marker}"


def test_demo_script_uses_only_documented_endpoints() -> None:
    """Скрипт не выдумывает API: адреса и пути есть в документации стека."""
    source = _text(SCRIPT)
    for endpoint in (
        "/api/v1/targets",
        "/api/v1/alerts",
        "/api/v2/alerts",
        "/alerts",
        "/healthz",
    ):
        assert endpoint in source, f"в скрипте нет {endpoint}"
    observability = _text(OBS_DOC)
    for endpoint in ("/api/v1/targets", "/api/v1/alerts", "/api/v2/alerts"):
        assert endpoint in observability, f"в docs/observability.md нет {endpoint}"


# --- разбор ответов сервисов ---------------------------------------------------


def test_target_health_and_missing_targets() -> None:
    """Цели разбираются по `labels.job`; DOWN и отсутствующие — в списке проблем."""
    with FakeServices({"/api/v1/targets": TARGETS_UP}) as services:
        health = target_health(services.url)
    assert health == {job: "up" for job in EXPECTED_TARGETS}
    assert missing_targets(health) == []

    broken = dict(health, **{"clikit-api": "down"})
    broken.pop("loki")
    assert sorted(missing_targets(broken)) == ["clikit-api", "loki"]


def test_alert_states_from_prometheus() -> None:
    """Состояния алерта берутся из `data.alerts`, чужие алерты игнорируются."""
    payload = {
        "status": "success",
        "data": {
            "alerts": [
                {"labels": {"alertname": ALERT_NAME}, "state": "pending"},
                {"labels": {"alertname": ALERT_NAME}, "state": "firing"},
                {"labels": {"alertname": "Other"}, "state": "firing"},
            ]
        },
    }
    with FakeServices({"/api/v1/alerts": payload}) as services:
        assert alert_states(services.url) == ["pending", "firing"]
        assert alert_states(services.url, "Other") == ["firing"]
        assert alert_states(services.url, "Missing") == []


def test_alertmanager_states_from_v2_api() -> None:
    """Alertmanager отдаёт список алертов с `status.state`."""
    payload = [
        {"labels": {"alertname": ALERT_NAME}, "status": {"state": "active"}},
        {"labels": {"alertname": "Other"}, "status": {"state": "active"}},
    ]
    with FakeServices({"/api/v2/alerts": payload}) as services:
        assert alertmanager_states(services.url) == ["active"]


def test_sink_states_from_local_receiver() -> None:
    """Приёмник отдаёт `{"alerts": [...]}`; статусы идут в порядке поступления."""
    payload = {
        "alerts": [
            {"alertname": ALERT_NAME, "status": "firing"},
            {"alertname": "Other", "status": "firing"},
            {"alertname": ALERT_NAME, "status": "resolved"},
        ]
    }
    with FakeServices({"/alerts": payload}) as services:
        assert sink_states(services.url) == ["firing", "resolved"]


def test_metric_total_sums_series_and_tolerates_empty() -> None:
    """Счётчик в демо — сумма серий; пустой результат не ошибка."""
    payload = {
        "status": "success",
        "data": {
            "result": [
                {"metric": {"route": "/v1/scenarios"}, "value": [0, "12"]},
                {"metric": {"route": "/healthz"}, "value": [0, "3"]},
                {"metric": {}, "value": [0, "not-a-number"]},
            ]
        },
    }
    with FakeServices({"/api/v1/query": payload}) as services:
        assert metric_total(services.url, "sum(x)") == pytest.approx(15.0)
    with FakeServices({"/api/v1/query": {"status": "success", "data": {}}}) as empty:
        assert metric_total(empty.url, "sum(x)") == 0.0


def test_unreachable_service_is_demo_error() -> None:
    """Недоступный сервис — понятная ошибка шага, а не трейсбек urllib."""
    with pytest.raises(DemoError, match="сервис недоступен"):
        target_health("http://127.0.0.1:1")


# --- ожидание и коды выхода ----------------------------------------------------


def test_wait_for_returns_elapsed_when_probe_passes() -> None:
    """Ожидание возвращает результат и время, а не спит фиксированно."""
    calls = {"count": 0}

    def probe() -> bool:
        calls["count"] += 1
        return calls["count"] >= 2

    elapsed, result = wait_for(probe, timeout=5, interval=0.01)
    assert result is True
    assert calls["count"] == 2
    assert elapsed < 5


def test_wait_for_times_out_with_describe() -> None:
    """Таймаут содержит, чего именно ждали, — это подсказка для оператора."""
    with pytest.raises(DemoError, match="ClikitApiDown"):
        wait_for(
            lambda: False,
            timeout=0.05,
            interval=0.01,
            describe="ClikitApiDown в состоянии firing (Prometheus)",
        )


def test_wait_for_survives_transient_errors() -> None:
    """Пока Prometheus перезапускается, опрос не падает — ждём дальше."""
    calls = {"count": 0}

    def probe() -> bool:
        calls["count"] += 1
        if calls["count"] == 1:
            raise DemoError("временная ошибка")
        return True

    _, result = wait_for(probe, timeout=5, interval=0.01)
    assert result is True


def test_main_returns_not_ready_for_missing_compose_file(tmp_path: Path) -> None:
    """Нет compose-файла — код 2 (условие, а не провал прогона)."""
    code = demo.main(["check", "--compose-file", str(tmp_path / "absent.yml")])
    assert code == EXIT_NOT_READY


@pytest.mark.parametrize(
    ("checks", "error", "expected"),
    [
        ([("a", True), ("b", True)], None, EXIT_OK),
        ([("a", True), ("b", False)], None, EXIT_FAILED),
        ([], "таймаут", EXIT_FAILED),
    ],
)
def test_result_exit_code(
    checks: list[tuple[str, bool]], error: str | None, expected: int
) -> None:
    """Код выхода: 0 только когда все проверки пройдены и ошибки нет."""
    result = DemoResult(checks=list(checks), error=error)
    assert result.exit_code == expected


def test_format_duration() -> None:
    """Длительность печатается как в таймлайне постмортема."""
    assert format_duration(0) == "0 с"
    assert format_duration(59.4) == "59 с"
    assert format_duration(90) == "1 мин 30 с"
    assert format_duration(3600) == "60 мин 00 с"


def test_timeline_collects_events_with_offsets() -> None:
    """Каждый шаг попадает в таймлайн — из него собирается отчёт демо."""
    lines: list[str] = []
    timeline = Timeline(echo=lines.append)
    timeline.log("стек готов")
    timeline.log("сломали")
    assert len(timeline.events) == 2
    assert timeline.events[0][1] == "стек готов"
    assert all(
        text in line for (_, text), line in zip(timeline.events, lines, strict=True)
    )


# --- готовность стека и аварийное восстановление -------------------------------


def test_check_stack_reports_missing_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Без `.env` compose не интерполирует секреты — это код 2, а не «демо упало»."""
    from scripts.observability_demo import check_stack

    def fake_compose(*args: Any, **kwargs: Any) -> None:
        raise DemoError(
            "config: код 1 (required variable POSTGRES_PASSWORD is missing a value)"
        )

    monkeypatch.setattr(demo, "compose", fake_compose)
    with pytest.raises(DemoError, match="compose-файл не читается"):
        check_stack(DemoOptions(), Timeline(echo=lambda _: None))


def test_run_demo_stops_before_traffic_when_stack_is_not_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Стек не готов: шаги с поломкой не выполняются, остаётся чистое состояние."""

    def fake_compose(*args: Any, **kwargs: Any) -> None:
        raise DemoError("docker не найден в PATH")

    calls: list[str] = []
    monkeypatch.setattr(demo, "compose", fake_compose)
    monkeypatch.setattr(demo, "break_api", lambda *_: calls.append("break"))
    result = run_demo(DemoOptions(), timeline=Timeline(echo=lambda _: None))
    assert result.not_ready is True
    assert result.checks == []
    assert calls == []
    assert result.exit_code == EXIT_FAILED
    assert "compose-файл не читается" in str(result.error)


def test_run_demo_restores_api_after_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Если демо упало после поломки, API всё равно возвращается в строй."""
    commands: list[tuple[str, ...]] = []

    def fake_compose(*args: Any, **kwargs: Any) -> None:
        commands.append(tuple(str(arg) for arg in args[1:]))

    monkeypatch.setattr(demo, "compose", fake_compose)
    monkeypatch.setattr(demo, "check_stack", lambda *_: None)
    monkeypatch.setattr(demo, "make_traffic", lambda *_: None)
    monkeypatch.setattr(demo, "break_api", lambda *_: commands.append(("stop", "api")))

    def failing_watch(*args: Any) -> None:
        raise DemoError("алерт не пришёл")

    monkeypatch.setattr(demo, "watch_firing", failing_watch)
    result = run_demo(DemoOptions(), timeline=Timeline(echo=lambda _: None))
    assert result.error == "алерт не пришёл"
    assert ("start", "api") in commands
    assert result.exit_code == EXIT_FAILED


def test_format_result_for_not_ready_stack() -> None:
    """Сводка объясняет, что демо не запущено, и не выдаёт это за провал."""
    result = DemoResult(error="нет .env", not_ready=True)
    text = format_result(result)
    assert "НЕ ЗАПУЩЕНО" in text
    assert "нет .env" in text


def test_demo_options_defaults_point_to_localhost() -> None:
    """Порты стека публикуются только на localhost (T2.1) — демо не ходит в сеть."""
    options = DemoOptions()
    for url in (
        options.prometheus_url,
        options.alertmanager_url,
        options.sink_url,
        options.api_url,
    ):
        assert url.startswith("http://127.0.0.1:"), url


def test_compose_file_is_the_only_stack_entrypoint() -> None:
    """Демо не поднимает второй проект: только включённый cloud-compose."""
    compose_text = _text(COMPOSE)
    assert "include:" in compose_text
    assert "docker-compose.cloud.yml" in compose_text
    assert "name: clikit-observability" in compose_text
