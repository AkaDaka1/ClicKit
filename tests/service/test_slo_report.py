"""Проверки отчёта по error budget (M8 T4.1, scripts/slo_report.py).

Скрипт — ворота политики §7: он читает recording rules ``clikit:slo_error_budget:*``
и переводит их в режим («норма / осторожно / заморозка / нарушение») и в код
выхода. Поэтому проверяется не только арифметика, но и связь с контрактом:
имена записей совпадают с `observability/prometheus/recording_rules.yml`, а
цифры бюджета и пороги — с `docs/sre/slo.md`.

Prometheus подменяется крошечным HTTP-сервером: сеть в тестах не нужна, а
формат ответа `/api/v1/query` (JSON) разбирается так же, как в жизни.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from types import TracebackType
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest
import yaml

from scripts.slo_report import (
    BUDGET_MINUTES,
    EXIT_EXHAUSTED,
    EXIT_FREEZE,
    EXIT_NO_DATA,
    EXIT_OK,
    OPTIONAL_RECORDS,
    POLICY,
    REQUIRED_RECORDS,
    BudgetReport,
    collect_report,
    exit_code_for,
    format_duration,
    format_report,
    main,
    parse_vector,
    policy_description,
    policy_state,
)

ROOT = Path(__file__).resolve().parents[2]
RECORDING_RULES = ROOT / "observability" / "prometheus" / "recording_rules.yml"
SLO_DOC = ROOT / "docs" / "sre" / "slo.md"

#: Значения, которые «отдаёт» поддельный Prometheus.
SAMPLE_VALUES: dict[str, float] = {
    "clikit:sli_availability:ratio_rate30d": 0.996,
    "clikit:slo_error_budget:consumed_ratio_30d": 0.8,
    "clikit:slo_error_budget:remaining_minutes_30d": 43.2,
    "clikit:slo_burn_rate:ratio_1h": 1.5,
    "clikit:slo_burn_rate:ratio_6h": 0.25,
}


class _QueryHandler(BaseHTTPRequestHandler):
    """Ответы на `/api/v1/query` по словарю `values` сервера."""

    def do_GET(self) -> None:  # noqa: N802 — имя метода задано stdlib
        values = getattr(self.server, "values", {})
        query = parse_qs(urlparse(self.path).query).get("query", [""])[0]
        result: list[dict[str, Any]] = []
        if query in values:
            result = [{"metric": {"__name__": query}, "value": [0, str(values[query])]}]
        body = {"status": "success", "data": {"resultType": "vector", "result": result}}
        payload = json.dumps(body).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args: Any) -> None:
        """Заглушить журнал HTTP-сервера в тестах."""


class FakePrometheus:
    """Поддельный Prometheus на свободном порту."""

    def __init__(self, values: dict[str, float]) -> None:
        self.server = HTTPServer(("127.0.0.1", 0), _QueryHandler)
        self.server.values = values  # type: ignore[attr-defined]
        self.host, self.port = self.server.server_address
        self._thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        """Базовый URL поддельного сервера."""
        return f"http://{self.host}:{self.port}"

    def __enter__(self) -> FakePrometheus:
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


# --- политика §7 и коды выхода -------------------------------------------------


@pytest.mark.parametrize(
    ("consumed", "expected"),
    [
        (None, "no-data"),
        (0.0, "normal"),
        (0.49, "normal"),
        (0.5, "careful"),
        (0.74, "careful"),
        (0.75, "freeze"),
        (0.99, "freeze"),
        (1.0, "exhausted"),
        (2.0, "exhausted"),
    ],
)
def test_policy_state_thresholds(consumed: float | None, expected: str) -> None:
    """Границы режимов — те же 50/75/100 %, что в политике §7."""
    assert policy_state(consumed) == expected


@pytest.mark.parametrize(
    ("consumed", "expected"),
    [
        (0.0, EXIT_OK),
        (0.6, EXIT_OK),
        (0.8, EXIT_FREEZE),
        (1.0, EXIT_EXHAUSTED),
        (2.0, EXIT_EXHAUSTED),
        (None, EXIT_NO_DATA),
    ],
)
def test_exit_code_matches_policy(consumed: float | None, expected: int) -> None:
    """Код выхода — контракт для будущего гейта деплоя M10."""
    assert exit_code_for(consumed) == expected


def test_every_policy_state_has_description() -> None:
    """У каждого режима есть понятное действие, а не пустая строка."""
    for _, state, description in POLICY:
        assert state
        assert description
        assert policy_description(POLICY[-1][0] - 0.01)  # нет данных


def test_policy_descriptions_cover_all_states() -> None:
    """Описание режима совпадает с состоянием и меняется по порогам."""
    for threshold, state, _ in POLICY:
        assert policy_state(threshold) == state
        assert policy_description(threshold)


@pytest.mark.parametrize(
    ("minutes", "expected"),
    [
        (216, "3 ч 36 мин"),
        (129.6, "2 ч 10 мин"),
        (43.2, "43 мин"),
        (-216, "-3 ч 36 мин"),
        (0, "0 мин"),
        (None, "нет данных"),
    ],
)
def test_format_duration(minutes: float | None, expected: str) -> None:
    """Минуты переводятся в «N ч M мин»; отрицательный остаток видно явно."""
    assert format_duration(minutes) == expected


# --- разбор ответа Prometheus --------------------------------------------------


def test_parse_vector_returns_value() -> None:
    """Значение берётся из единственной серии вектора."""
    payload = {
        "status": "success",
        "data": {"resultType": "vector", "result": [{"value": [1, "0.216"]}]},
    }
    assert parse_vector(payload) == pytest.approx(0.216)


def test_parse_vector_empty_result_is_none() -> None:
    """Пустой результат — это «нет данных», а не ноль: ноль = бюджет целый."""
    payload = {"status": "success", "data": {"result": []}}
    assert parse_vector(payload) is None


@pytest.mark.parametrize(
    "payload",
    [
        {"status": "error", "data": {}},
        {"status": "success", "data": {"result": [{"value": [1]}]}},
        {"status": "success", "data": {"result": [{"value": [1, "abc"]}]}},
    ],
)
def test_parse_vector_rejects_broken_payload(payload: dict[str, Any]) -> None:
    """Битый ответ не превращается в «всё хорошо»."""
    with pytest.raises(ValueError):
        parse_vector(payload)


# --- отчёт против поддельного Prometheus ---------------------------------------


def test_collect_report_reads_all_records() -> None:
    """Отчёт собирается из записей recording rules, а не из своей формулы."""
    with FakePrometheus(dict(SAMPLE_VALUES)) as prometheus:
        report = collect_report(prometheus.url)
    assert report.availability == pytest.approx(0.996)
    assert report.consumed == pytest.approx(0.8)
    assert report.remaining_minutes == pytest.approx(43.2)
    assert report.burn_rate_1h == pytest.approx(1.5)
    assert report.burn_rate_6h == pytest.approx(0.25)
    assert report.state == "freeze"
    assert report.exit_code == EXIT_FREEZE


def test_report_survives_missing_optional_records() -> None:
    """Без burn rate отчёт остаётся полезным: отсутствие записи — `None`."""
    required = {name: SAMPLE_VALUES[name] for name in REQUIRED_RECORDS}
    with FakePrometheus(required) as prometheus:
        report = collect_report(prometheus.url)
    assert report.burn_rate_1h is None
    assert report.burn_rate_6h is None
    assert report.state == "freeze"


def test_format_report_shows_budget_and_policy() -> None:
    """Текстовый отчёт содержит проценты, минуты, режим и код выхода."""
    report = BudgetReport(
        availability=0.996,
        consumed=0.8,
        remaining_minutes=43.2,
        burn_rate_1h=1.5,
        burn_rate_6h=0.25,
    )
    text = format_report(report)
    assert "99.600 %" in text
    assert "80.0 %" in text
    assert "43.2 мин" in text
    assert "43 мин из 216 мин" in text
    assert "freeze" in text
    assert "1.50x" in text
    assert f"Код выхода: {EXIT_FREEZE}" in text


def test_main_json_returns_policy_exit_code() -> None:
    """`main --json` печатает машинный отчёт и возвращает код политики."""
    with FakePrometheus(dict(SAMPLE_VALUES)) as prometheus:
        code = main(["--prometheus-url", prometheus.url, "--json", "--timeout", "5"])
    assert code == EXIT_FREEZE


def test_main_reports_no_data_when_prometheus_down() -> None:
    """Недоступный Prometheus — это 3, а не «бюджет целый»."""
    code = main(["--prometheus-url", "http://127.0.0.1:1", "--timeout", "0.5"])
    assert code == EXIT_NO_DATA


def test_main_reports_no_data_for_empty_series() -> None:
    """Записи есть, но данных нет — тоже 3."""
    with FakePrometheus({}) as prometheus:
        code = main(["--prometheus-url", prometheus.url])
    assert code == EXIT_NO_DATA


# --- связь с контрактом (правила и документ) -----------------------------------


def _recorded_names() -> set[str]:
    """Имена записей из recording rules Prometheus."""
    data = yaml.safe_load(RECORDING_RULES.read_text(encoding="utf-8"))
    return {rule["record"] for group in data["groups"] for rule in group["rules"]}


def test_script_reads_existing_recording_rules() -> None:
    """Скрипт читает только те записи, которые реально считаются Prometheus."""
    recorded = _recorded_names()
    for name in REQUIRED_RECORDS + OPTIONAL_RECORDS:
        assert name in recorded, f"нет записи {name}"


def test_budget_minutes_match_slo_document() -> None:
    """216 минут и бюджет 0.5 % — одна цифра в скрипте и в SLO-документе."""
    text = SLO_DOC.read_text(encoding="utf-8")
    assert BUDGET_MINUTES == 216
    assert "216 мин" in text
    assert "0.005" in text


def test_policy_thresholds_match_slo_document() -> None:
    """Пороги политики в скрипте — те же 50/75/100 %, что в §7."""
    text = SLO_DOC.read_text(encoding="utf-8")
    thresholds = sorted(threshold for threshold, _, _ in POLICY if threshold > 0)
    assert thresholds == [0.5, 0.75, 1.0]
    for fragment in ("< 50 %", "50–75 %", "75–100 %", "≥ 100 %"):
        assert fragment in text, f"в docs/sre/slo.md нет {fragment!r}"


def test_script_has_no_secrets() -> None:
    """В скрипте нет ключей и паролей: он читает только метрики Prometheus."""
    text = (ROOT / "scripts" / "slo_report.py").read_text(encoding="utf-8")
    for marker in ("CLICKIT_API_KEY", "POSTGRES_PASSWORD", "X-API-Key", "api_key"):
        assert marker not in text, f"в slo_report.py похоже на секрет ({marker})"
