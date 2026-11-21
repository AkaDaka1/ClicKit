"""Статические проверки правил алертов и маршрутизации (M8 T3.1).

Живой чекпоинт T3.1 — `stop api` → `ClikitApiDown` в состоянии firing виден в
Alertmanager и в приёмнике, возврат сервиса → resolved. Эти тесты страхуют
конфигурацию от регрессий, которые видны только при ручном запуске:
правила не смонтированы в Prometheus, порог разошёлся с SLO, алерт без
`severity`/`for`, забытая маршрутизация, секрет в YAML или битая ссылка
`runbook.md`.

Синтаксис и семантику правил (окна `for`, resolved) проверяет `promtool`
(см. `docs/sre/slo.md` §9); здесь — дешёвые инварианты и связи с SLO.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
ALERTS = ROOT / "observability" / "prometheus" / "alerts.yml"
ALERTMANAGER = ROOT / "observability" / "alertmanager" / "alertmanager.yml"
PROMETHEUS = ROOT / "observability" / "prometheus" / "prometheus.yml"
RECORDING = ROOT / "observability" / "prometheus" / "recording_rules.yml"
RULE_TESTS = ROOT / "observability" / "prometheus" / "tests" / "alerts_test.yml"
SLO_DOC = ROOT / "docs" / "sre" / "slo.md"

#: Полный набор алертов — контракт: имя живёт в runbook, демо и в
#: Alertmanager-inhibition, поэтому переименование не должно быть тихим.
EXPECTED_ALERTS = {
    "ClikitApiDown",
    "FastErrorBudgetBurn",
    "SlowErrorBudgetBurn",
    "High5xxRate",
    "HighScenarioLatency",
    "DbPoolExhausted",
    "HostMemoryLow",
}
#: severity, которые понимает маршрутизация Alertmanager.
SEVERITIES = {"critical", "warning"}

_METRIC = re.compile(r"\bclikit_[a-z0-9_]+\b")
_RECORD = re.compile(r"\bclikit:[a-z0-9_:]+\b")
#: Метрики сервиса (docs/sre/slo.md §8) — алерты по ним считаются напрямую.
SERVICE_METRICS = {"clikit_db_pool_connections"}
#: Метрики, которые сервис не отдаёт и которые осознанно используются:
#: `up` — состояние target'а Prometheus (падение API SLI не видит),
#: `node_memory_*` — память Docker-хоста (node-exporter).
EXTERNAL_METRICS = {
    "up",
    "node_memory_MemAvailable_bytes",
    "node_memory_MemTotal_bytes",
}


def _yaml(path: Path) -> dict[str, Any]:
    """Прочитать YAML-файл как словарь."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict), f"{path.name}: ожидается YAML-объект"
    return data


def _alert_rules() -> list[dict[str, Any]]:
    """Плоский список правил алертов (все группы)."""
    data = _yaml(ALERTS)
    return [rule for group in data["groups"] for rule in group["rules"]]


def _records() -> set[str]:
    """Набор записей recording rules — алерты обязаны читать только их."""
    data = _yaml(RECORDING)
    return {rule["record"] for group in data["groups"] for rule in group["rules"]}


def test_alert_rules_match_contract() -> None:
    """Набор алертов совпадает с контрактом: без тихих переименований."""
    names = {rule["alert"] for rule in _alert_rules()}
    assert names == EXPECTED_ALERTS


def test_alert_rules_have_severity_and_for() -> None:
    """У каждого алерта есть severity из известных и окно `for` (анти-шум)."""
    for rule in _alert_rules():
        severity = rule["labels"]["severity"]
        assert severity in SEVERITIES, f"{rule['alert']}: severity {severity!r}"
        assert rule.get("for"), f"{rule['alert']}: нет окна `for`"
        assert rule["expr"].strip(), f"{rule['alert']}: пустое выражение"
        assert rule["annotations"]["summary"], f"{rule['alert']}: нет summary"


def test_alert_thresholds_match_slo() -> None:
    """Пороги в правилах совпадают с цифрами SLO, а не «примерно похожи»."""
    expressions = {rule["alert"]: rule["expr"] for rule in _alert_rules()}
    assert "14.4" in expressions["FastErrorBudgetBurn"]
    assert "6" in expressions["SlowErrorBudgetBurn"]
    assert "0.01" in expressions["High5xxRate"]
    assert "0.3" in expressions["HighScenarioLatency"]
    # Те же цифры обязаны быть в документе SLO (T0.1 держит их контрактом).
    slo = SLO_DOC.read_text(encoding="utf-8")
    for fragment in ("**14.4**", "**6**", "**300 мс**", "1 %"):
        assert fragment in slo, f"в docs/sre/slo.md нет {fragment!r}"


def test_alert_rules_read_only_recording_rules_and_known_metrics() -> None:
    """Формулы не копируются: алерты читают записи SLO и метрики сервиса."""
    records = _records()
    for rule in _alert_rules():
        used_metrics = set(_METRIC.findall(rule["expr"]))
        used_records = set(_RECORD.findall(rule["expr"]))
        used_external = {name for name in EXTERNAL_METRICS if name in rule["expr"]}
        assert used_metrics <= SERVICE_METRICS, (
            f"{rule['alert']}: неизвестные метрики {used_metrics}"
        )
        assert used_records <= records, (
            f"{rule['alert']}: ссылка на несуществующую запись {used_records}"
        )
        assert used_metrics or used_records or used_external, (
            f"{rule['alert']}: нет ни метрики, ни записи"
        )


def test_prometheus_loads_alert_rules() -> None:
    """Файл алертов смонтирован в Prometheus, иначе правила «мёртвые»."""
    rule_files = _yaml(PROMETHEUS)["rule_files"]
    assert "/etc/prometheus/recording_rules.yml" in rule_files
    assert "/etc/prometheus/alerts.yml" in rule_files


def test_alertmanager_routes_by_severity_to_sink() -> None:
    """Оба severity уходят в локальный приёмник; critical повторяется чаще."""
    route = _yaml(ALERTMANAGER)["route"]
    assert route["receiver"] == "local-sink"
    routes = {item["matchers"][0]: item for item in route["routes"]}
    assert 'severity="critical"' in routes
    assert 'severity="warning"' in routes
    critical = routes['severity="critical"']
    warning = routes['severity="warning"']
    assert critical["repeat_interval"] == "1h"
    assert warning["repeat_interval"] == "4h"
    receivers = {item["name"]: item for item in _yaml(ALERTMANAGER)["receivers"]}
    webhook = receivers["local-sink"]["webhook_configs"][0]
    assert webhook["url"] == "http://alert-sink:8080/webhook"
    assert webhook["send_resolved"] is True


def test_alertmanager_inhibits_derived_alerts() -> None:
    """Падение API подавляет следствия (5xx, латентность, пул) — не шумим."""
    inhibit = _yaml(ALERTMANAGER)["inhibit_rules"]
    assert inhibit, "нет правил подавления"
    rule = inhibit[0]
    assert 'alertname="ClikitApiDown"' in rule["source_matchers"]
    targets = rule["target_matchers"][0]
    for derived in (
        "High5xxRate",
        "FastErrorBudgetBurn",
        "SlowErrorBudgetBurn",
        "HighScenarioLatency",
        "DbPoolExhausted",
    ):
        assert derived in targets, f"в подавлении нет {derived}"


def test_runbook_links_from_alerts_test_are_documented() -> None:
    """Алерты описаны в docs/sre/slo.md §11 (иначе имя живёт только в YAML)."""
    slo = SLO_DOC.read_text(encoding="utf-8")
    for name in EXPECTED_ALERTS:
        assert name in slo, f"в docs/sre/slo.md нет алерта {name}"


def test_promtool_alert_tests_cover_the_rules() -> None:
    """promtool-тесты ссылаются на файл алертов и покрывают каждый алерт."""
    data = yaml.safe_load(RULE_TESTS.read_text(encoding="utf-8"))
    assert "../alerts.yml" in data["rule_files"]
    checked: set[str] = set()
    for case in data["tests"]:
        for check in case["alert_rule_test"]:
            checked.add(check["alertname"])
    assert EXPECTED_ALERTS <= checked, f"не покрыты: {EXPECTED_ALERTS - checked}"


def test_no_secrets_or_high_cardinality_labels() -> None:
    """В правилах и маршрутизации нет ключей и id сценариев."""
    for path in (ALERTS, ALERTMANAGER, RULE_TESTS):
        text = path.read_text(encoding="utf-8")
        assert "CLICKIT_API_KEY=" not in text, f"{path.name}: похоже на секрет"
        assert "POSTGRES_PASSWORD=" not in text, f"{path.name}: похоже на секрет"
        assert "X-API-Key" not in text, f"{path.name}: похоже на ключ"
    for rule in _alert_rules():
        assert "scenario_id" not in rule["expr"]
        assert "request_id" not in rule["expr"]
