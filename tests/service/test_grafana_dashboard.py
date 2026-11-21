"""Статические проверки дашборда Grafana (M8 T2.2).

Живой чекпоинт T2.2 — дашборд открывается в Grafana и показывает трафик
(скриншот в README). Эти тесты страхуют «дашборд как код» от тихих регрессий:
несуществующий datasource, панель без запроса, формулу SLO, скопированную
в JSON вместо recording rule, метку с id сценария или секрет в файле.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
DASHBOARD = ROOT / "observability" / "grafana" / "dashboards" / "clikit-cloud.json"
PROVIDER = (
    ROOT
    / "observability"
    / "grafana"
    / "provisioning"
    / "dashboards"
    / "dashboards.yml"
)
DATASOURCES = (
    ROOT
    / "observability"
    / "grafana"
    / "provisioning"
    / "datasources"
    / "datasources.yml"
)
RECORDING_RULES = ROOT / "observability" / "prometheus" / "recording_rules.yml"
README = ROOT / "README.md"

#: Панели, без которых дашборд не выполняет чекпоинт T2.2/T4.1.
REQUIRED_TITLES = (
    "RPS по маршрутам",
    "Error rate (5xx)",
    "Задержка запросов: p50 / p95 / p99",
    "In-flight и пул БД",
    "CPU и память Docker-хоста",
    "Доступность 30 дней",
    "Остаток бюджета, мин",
    "Режим политики бюджета",
)
#: Datasource, которые реально провизионируются в T2.1.
DATASOURCE_UIDS = {"prometheus", "loki", "tempo"}
#: Метрики сервиса из контракта T1.2 (docs/sre/slo.md §8).
SERVICE_METRICS = {
    "clikit_http_requests_total",
    "clikit_http_request_duration_seconds_bucket",
    "clikit_http_requests_in_flight",
    "clikit_db_pool_connections",
    "clikit_build_info",
}
#: Формулы SLO живут в recording rules, а не в дашборде (ADR №60).
SLO_METRICS = {
    "clikit:http_requests:rate5m",
    "clikit:http_errors:ratio_rate5m",
    "clikit:sli_availability:ratio_rate30d",
    "clikit:slo_burn_rate:ratio_1h",
    "clikit:slo_burn_rate:ratio_6h",
    "clikit:slo_error_budget:remaining_minutes_30d",
    "clikit:slo_error_budget:policy_state_30d",
}
_METRIC = re.compile(r"\bclikit_[a-z0-9_]+\b")
_RECORD = re.compile(r"\bclikit:[a-z0-9_:]+\b")


def _dashboard() -> dict[str, Any]:
    """Разобрать JSON-дашборда как словарь."""
    data = json.loads(DASHBOARD.read_text(encoding="utf-8"))
    assert isinstance(data, dict), "дашборд должен быть объектом JSON"
    return data


def _targets(panel: dict[str, Any]) -> list[dict[str, Any]]:
    """Получить запросы панели."""
    return panel.get("targets", [])


def test_dashboard_is_provisioned_from_git() -> None:
    """Провайдер read-only указывает на каталог с JSON-дашбордом."""
    provider = yaml.safe_load(PROVIDER.read_text(encoding="utf-8"))
    settings = provider["providers"][0]
    assert settings["type"] == "file"
    assert settings["options"]["path"] == "/var/lib/grafana/dashboards"
    assert settings["allowUiUpdates"] is False
    assert settings["updateIntervalSeconds"] <= 60
    assert DASHBOARD.name == "clikit-cloud.json"


def test_dashboard_metadata_is_stable() -> None:
    """UID и версия фиксированы: на них ссылаются скриншот и будущие алерты."""
    dashboard = _dashboard()
    assert dashboard["uid"] == "clikit-cloud"
    assert dashboard["title"]
    assert dashboard["editable"] is False
    assert dashboard["schemaVersion"] >= 40
    assert dashboard["refresh"] == "30s"


def test_dashboard_covers_required_panels() -> None:
    """Приёмка T2.2: RPS, error rate, latency, in-flight, БД, CPU/RAM."""
    titles = {panel["title"] for panel in _dashboard()["panels"]}
    assert set(REQUIRED_TITLES) <= titles, (
        f"нет панелей: {set(REQUIRED_TITLES) - titles}"
    )


def test_every_panel_has_query_and_known_datasource() -> None:
    """Пустая панель или datasource с опечаткой в uid не должен попасть в Git."""
    configured = yaml.safe_load(DATASOURCES.read_text(encoding="utf-8"))
    uids = {item["uid"] for item in configured["datasources"]}
    assert uids == DATASOURCE_UIDS
    dashboards = _dashboard()
    identifiers = [panel["id"] for panel in dashboards["panels"]]
    assert len(identifiers) == len(set(identifiers)), "дубли id панелей"
    for panel in dashboards["panels"]:
        uid = panel.get("datasource", {}).get("uid")
        assert uid in uids, f"{panel['title']}: неизвестный datasource {uid}"
        targets = _targets(panel)
        assert targets, f"{panel['title']}: нет запросов"
        for target in targets:
            assert target.get("expr"), f"{panel['title']}: пустой expr"


def test_dashboard_uses_recording_rules_for_slo() -> None:
    """SLO-формулы берутся из правил T0.1, а не копируются в JSON."""
    rules = yaml.safe_load(RECORDING_RULES.read_text(encoding="utf-8"))
    recorded = {rule["record"] for group in rules["groups"] for rule in group["rules"]}
    used = set()
    for panel in _dashboard()["panels"]:
        for target in _targets(panel):
            used |= set(_RECORD.findall(target["expr"]))
    assert SLO_METRICS <= recorded
    assert SLO_METRICS <= used
    # Раньше в дашборде была формула 1 - ratio30d; теперь только запись.
    formulas = " ".join(
        target["expr"] for panel in _dashboard()["panels"] for target in _targets(panel)
    )
    assert "0.005" not in formulas, "бюджет считается в recording rules, не в дашборде"


def test_dashboard_uses_only_known_metrics() -> None:
    """Все метрики — из контракта T1.2 или recording rules T0.1."""
    rules = yaml.safe_load(RECORDING_RULES.read_text(encoding="utf-8"))
    recorded = {rule["record"] for group in rules["groups"] for rule in group["rules"]}
    allowed = SERVICE_METRICS | recorded
    for panel in _dashboard()["panels"]:
        for target in _targets(panel):
            unknown = set(_METRIC.findall(target["expr"])) - allowed
            assert not unknown, f"{panel['title']}: неизвестные метрики {unknown}"


def test_no_high_cardinality_labels_or_secrets() -> None:
    """В запросах нет id сценариев/request_id, а в JSON — ключей и паролей."""
    text = DASHBOARD.read_text(encoding="utf-8")
    for secret in ("CLICKIT_API_KEY=", "POSTGRES_PASSWORD=", "X-API-Key", "xoxb-"):
        assert secret not in text, f"в дашборде найдено {secret}"
    for panel in _dashboard()["panels"]:
        for target in _targets(panel):
            expr = target["expr"]
            assert "scenario_id" not in expr and "request_id" not in expr
            assert "X-Request-ID" not in expr and "api_key" not in expr


def test_readme_has_dashboard_screenshot() -> None:
    """Скриншот дашборда — часть чекпоинта T2.2 и виден в README."""
    text = README.read_text(encoding="utf-8")
    assert "screenshot-dashboard.png" in text
    image = ROOT / "docs" / "img" / "screenshot-dashboard.png"
    assert image.is_file() and image.stat().st_size > 10_000, "нет скриншота дашборда"
