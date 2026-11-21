"""Статические проверки SLO-документа и recording rules (M8 T0.1, T4.1).

Цифры SLO и PromQL-запросы — контракт (ADR №40), поэтому они проверяются
тестом: документ, recording rules и unit-тесты `promtool` не должны
разъезжаться между собой. Здесь — дешёвые инварианты, которые ловят опечатку
до запуска контейнера; синтаксис и семантику запросов проверяет `promtool`
(см. `docs/sre/slo.md` §9).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
SLO_DOC = ROOT / "docs" / "sre" / "slo.md"
RULES = ROOT / "observability" / "prometheus" / "recording_rules.yml"
RULE_TESTS = ROOT / "observability" / "prometheus" / "tests" / "slo_rules_test.yml"

# Полный набор записей — контракт: переименование без правки документа и
# тестов должно ломать сборку, а не дашборд в проде.
EXPECTED_RECORDS = {
    "clikit:http_requests:rate5m",
    "clikit:http_errors:ratio_rate5m",
    "clikit:sli_availability:ratio_rate5m",
    "clikit:sli_availability:ratio_rate1h",
    "clikit:sli_availability:ratio_rate6h",
    "clikit:sli_availability:ratio_rate30d",
    "clikit:sli_latency:ratio_rate5m",
    "clikit:sli_latency:ratio_rate30d",
    "clikit:sli_latency:p95_rate5m",
    "clikit:slo_burn_rate:ratio_1h",
    "clikit:slo_burn_rate:ratio_6h",
    "clikit:slo_error_budget:consumed_ratio_30d",
    # T4.1: остаток бюджета и режим политики §7.
    "clikit:slo_error_budget:remaining_ratio_30d",
    "clikit:slo_error_budget:remaining_minutes_30d",
    "clikit:slo_error_budget:policy_state_30d",
}

# Метрики, которые сервис отдаёт сам (T1.2). Всё остальное в правилах —
# опечатка или забытая запись.
SOURCE_METRICS = {
    "clikit_http_requests_total",
    "clikit_http_request_duration_seconds_bucket",
}

_METRIC = re.compile(r"\bclikit_[a-z0-9_]+\b")
_RECORD = re.compile(r"\bclikit:[a-z0-9_:]+\b")


def _text(path: Path) -> str:
    """Прочитать файл репозитория в UTF-8."""
    return path.read_text(encoding="utf-8")


def _rules() -> list[dict[str, Any]]:
    """Разобрать recording rules в плоский список правил."""
    data = yaml.safe_load(_text(RULES))
    return [rule for group in data["groups"] for rule in group["rules"]]


def _groups() -> dict[str, dict[str, Any]]:
    """Разобрать recording rules по группам."""
    data = yaml.safe_load(_text(RULES))
    return {group["name"]: group for group in data["groups"]}


def test_slo_document_states_contract_numbers() -> None:
    """Документ содержит цифры SLO, бюджета и политики, а не отсылки «см. код»."""
    text = _text(SLO_DOC)
    for fragment in (
        "**99.5 %**",
        "**0.5 % = 216 мин = 3 ч 36 мин**",
        "**300 мс**",
        "**95 %**",
        "30 дней",
        "**14.4**",
        "**6**",
        "7.2 мин",
        "50.4 мин",
        "9.3 %",
        "40 дней",
        "0.005",
    ):
        assert fragment in text, f"в docs/sre/slo.md нет {fragment!r}"


def test_slo_document_names_every_recording_rule() -> None:
    """Каждая запись из правил упомянута в документе (иначе она «ничья»)."""
    text = _text(SLO_DOC)
    for rule in _rules():
        assert rule["record"] in text, f"в документе нет {rule['record']}"


def test_recording_rules_match_contract() -> None:
    """Набор записей совпадает с контрактом: без тихих переименований."""
    names = {rule["record"] for rule in _rules()}
    assert names == EXPECTED_RECORDS


def test_recording_rules_use_only_known_metrics() -> None:
    """Правила считают только метрики сервиса, а не выдуманные имена."""
    for rule in _rules():
        used = set(_METRIC.findall(rule["expr"]))
        assert used <= SOURCE_METRICS, f"{rule['record']}: неизвестные метрики {used}"


def test_recording_rules_are_grouped_and_not_empty() -> None:
    """SLI считаются часто, SLO/burn rate — раз в минуту; выражения не пустые."""
    groups = _groups()
    assert set(groups) == {"clikit-sli", "clikit-slo"}
    assert groups["clikit-sli"]["interval"] == "15s"
    assert groups["clikit-slo"]["interval"] == "1m"
    for rule in _rules():
        assert rule["record"].startswith("clikit:")
        assert rule["expr"].strip(), f"{rule['record']}: пустое выражение"


def test_promtool_unit_tests_reference_existing_rules() -> None:
    """promtool-тесты ссылаются на реальные записи и покрывают семантику SLI."""
    data = yaml.safe_load(_text(RULE_TESTS))
    assert data["rule_files"] == ["../recording_rules.yml"]
    assert len(data["tests"]) >= 4
    for case in data["tests"]:
        for check in case["promql_expr_test"]:
            referenced = set(_RECORD.findall(check["expr"]))
            assert referenced, f"тест {case['name']!r} не ссылается на запись"
            assert referenced <= EXPECTED_RECORDS, (
                f"тест {case['name']!r} ссылается на неизвестную запись {referenced}"
            )


def test_slo_document_links_exist() -> None:
    """Относительные ссылки в документе не битые."""
    text = _text(SLO_DOC)
    for target in re.findall(r"\]\(([^)#\s]+)(?:#[^)]*)?\)", text):
        if target.startswith(("http://", "https://", "mailto:")):
            continue
        assert (SLO_DOC.parent / target).resolve().exists(), f"нет {target}"


def test_slo_document_has_no_secrets() -> None:
    """В документе и правилах нет ключей и секретов."""
    for path in (SLO_DOC, RULES, RULE_TESTS):
        text = _text(path)
        assert "CLICKIT_API_KEY" not in text
        assert "X-API-Key" not in text
