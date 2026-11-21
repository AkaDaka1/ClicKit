"""Отчёт по error budget ClicKit Cloud (M8 T4.1).

Считает то, что обещает `docs/sre/slo.md`: доступность за 30 дней,
израсходованную часть бюджета, остаток в минутах, режим политики §7 и burn
rate. Значения берутся из recording rules Prometheus
(`observability/prometheus/recording_rules.yml`) — формулы здесь не
дублируются, скрипт только читает готовые записи и переводит их в понятный
вид и в код выхода.

Зачем это отдельным скриптом:

* политика §7 («норма / осторожно / заморозка / нарушение») должна быть
  проверяема командой, а не глазами по дашборду;
* в M10 (доставка) тот же код выхода годится воротами деплоя: при заморозке
  рискованный релиз не должен выезжать «потому что успел»;
* расчёт на 30 дней виден в терминале, даже если Grafana не открыта.

Примеры:
    python scripts/slo_report.py
    python scripts/slo_report.py --prometheus-url http://127.0.0.1:9090
    python scripts/slo_report.py --json

Коды выхода:
    0 — режим normal или careful: изменения разрешены;
    1 — freeze: только исправления надёжности;
    2 — exhausted: SLO нарушен, постмортем обязателен;
    3 — нет данных или Prometheus недоступен (это не «всё хорошо»).

URL по умолчанию — `http://127.0.0.1:9090` (стек наблюдаемости публикует
порт только на localhost), переопределяется `--prometheus-url` или
переменной `CLICKIT_PROMETHEUS_URL`.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

#: URL Prometheus по умолчанию (localhost-порт стека наблюдаемости).
DEFAULT_URL = "http://127.0.0.1:9090"

#: Коды выхода — контракт скрипта, на них опираются тесты и будущий гейт M10.
EXIT_OK = 0
EXIT_FREEZE = 1
EXIT_EXHAUSTED = 2
EXIT_NO_DATA = 3

#: Записи, которые читает отчёт. Имена — контракт recording rules (T0.1/T4.1).
REQUIRED_RECORDS = (
    "clikit:sli_availability:ratio_rate30d",
    "clikit:slo_error_budget:consumed_ratio_30d",
    "clikit:slo_error_budget:remaining_minutes_30d",
)
OPTIONAL_RECORDS = (
    "clikit:slo_burn_rate:ratio_1h",
    "clikit:slo_burn_rate:ratio_6h",
)

#: Полный бюджет в минутах: 30 дней · 0.5 % = 43200 · 0.005 (docs/sre/slo.md §5).
BUDGET_MINUTES = 216

#: Пороги политики §7: режим и краткое описание действий.
POLICY: tuple[tuple[float, str, str], ...] = (
    (1.0, "exhausted", "SLO нарушен: постмортем обязателен, приоритет — надёжность"),
    (0.75, "freeze", "заморозка: только исправления надёжности"),
    (0.5, "careful", "осторожно: ревью изменений, влияющих на 5xx и латентность"),
    (0.0, "normal", "обычный поток изменений"),
)


@dataclass(frozen=True)
class BudgetReport:
    """Снимок error budget на момент запроса.

    Attributes:
        availability: SLI доступности за 30 дней (0…1) или `None`, если записи нет.
        consumed: израсходованная часть бюджета (0…1, больше 1 — нарушение).
        remaining_minutes: остаток бюджета в минутах простоя.
        burn_rate_1h: burn rate за час или `None`.
        burn_rate_6h: burn rate за 6 часов или `None`.
    """

    availability: float | None
    consumed: float | None
    remaining_minutes: float | None
    burn_rate_1h: float | None = None
    burn_rate_6h: float | None = None

    @property
    def state(self) -> str:
        """Режим политики §7 по израсходованной части бюджета."""
        return policy_state(self.consumed)

    @property
    def mode_description(self) -> str:
        """Человекочитаемое описание режима."""
        return policy_description(self.consumed)

    @property
    def exit_code(self) -> int:
        """Код выхода для гейта деплоя."""
        return exit_code_for(self.consumed)


def policy_state(consumed: float | None) -> str:
    """Определить режим политики по израсходованной части бюджета.

    Args:
        consumed: доля израсходованного бюджета (0 — целый, 1 — исчерпан).

    Returns:
        `normal`, `careful`, `freeze`, `exhausted` или `no-data`, если значения нет.
    """
    if consumed is None:
        return "no-data"
    for threshold, state, _ in POLICY:
        if consumed >= threshold:
            return state
    return "normal"


def policy_description(consumed: float | None) -> str:
    """Описание действий для текущего режима (политика §7)."""
    if consumed is None:
        return "нет данных: поднимите стек наблюдаемости и повторите"
    for threshold, _, description in POLICY:
        if consumed >= threshold:
            return description
    return POLICY[-1][2]


def exit_code_for(consumed: float | None) -> int:
    """Код выхода скрипта по израсходованной части бюджета."""
    state = policy_state(consumed)
    if state == "no-data":
        return EXIT_NO_DATA
    if state == "exhausted":
        return EXIT_EXHAUSTED
    if state == "freeze":
        return EXIT_FREEZE
    return EXIT_OK


def format_duration(minutes: float | None) -> str:
    """Перевести минуты в «N ч M мин» (для читаемого отчёта)."""
    if minutes is None:
        return "нет данных"
    sign = "-" if minutes < 0 else ""
    total = int(round(abs(minutes)))
    hours, remainder = divmod(total, 60)
    if hours:
        return f"{sign}{hours} ч {remainder} мин"
    return f"{sign}{remainder} мин"


def parse_vector(payload: Mapping[str, Any]) -> float | None:
    """Достать единственное значение из ответа Prometheus `/api/v1/query`.

    Args:
        payload: JSON-ответ Prometheus.

    Returns:
        Значение первой серии или `None`, если серия пуста.

    Raises:
        ValueError: ответ не в формате Prometheus или значение не число.
    """
    if payload.get("status") != "success":
        raise ValueError(f"Prometheus вернул status={payload.get('status')!r}")
    data = payload.get("data") or {}
    result = data.get("result") or []
    if not result:
        return None
    value = result[0].get("value") or []
    if len(value) != 2:
        raise ValueError(f"неожиданный элемент value: {value!r}")
    try:
        return float(value[1])
    except (TypeError, ValueError) as exc:
        raise ValueError(f"значение не число: {value[1]!r}") from exc


def query_value(
    prometheus_url: str,
    expression: str,
    *,
    timeout: float = 5.0,
) -> float | None:
    """Выполнить PromQL-запрос и вернуть одно числовое значение.

    Args:
        prometheus_url: Базовый URL Prometheus.
        expression: PromQL-выражение (обычно имя recording rule).
        timeout: Таймаут HTTP-запроса в секундах.

    Returns:
        Значение запроса или `None`, если серия отсутствует.

    Raises:
        urllib.error.URLError: Prometheus недоступен.
        ValueError: Некорректный ответ.
    """
    query = urllib.parse.urlencode({"query": expression})
    url = f"{prometheus_url.rstrip('/')}/api/v1/query?{query}"
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return parse_vector(payload)


def collect_report(prometheus_url: str, *, timeout: float = 5.0) -> BudgetReport:
    """Собрать отчёт по всем нужным записям Prometheus.

    Args:
        prometheus_url: Базовый URL Prometheus.
        timeout: Таймаут одного запроса в секундах.

    Returns:
        Снимок error budget; отсутствующие записи — `None`.
    """
    values = {
        name: query_value(prometheus_url, name, timeout=timeout)
        for name in REQUIRED_RECORDS + OPTIONAL_RECORDS
    }
    return BudgetReport(
        availability=values["clikit:sli_availability:ratio_rate30d"],
        consumed=values["clikit:slo_error_budget:consumed_ratio_30d"],
        remaining_minutes=values["clikit:slo_error_budget:remaining_minutes_30d"],
        burn_rate_1h=values["clikit:slo_burn_rate:ratio_1h"],
        burn_rate_6h=values["clikit:slo_burn_rate:ratio_6h"],
    )


def report_as_dict(report: BudgetReport) -> dict[str, Any]:
    """Представить отчёт как словарь для `--json`."""
    return {
        "state": report.state,
        "description": report.mode_description,
        "availability": report.availability,
        "consumed_ratio": report.consumed,
        "remaining_minutes": report.remaining_minutes,
        "budget_minutes": BUDGET_MINUTES,
        "burn_rate_1h": report.burn_rate_1h,
        "burn_rate_6h": report.burn_rate_6h,
        "exit_code": report.exit_code,
    }


def format_report(report: BudgetReport) -> str:
    """Собрать текстовый отчёт для терминала."""
    lines = [
        "ClicKit Cloud — error budget (SLO 99.5 %, окно 30 дней)",
        "",
    ]
    if report.availability is None:
        lines.append("  доступность:        нет данных")
    else:
        lines.append(f"  доступность:        {report.availability * 100:.3f} %")
    if report.consumed is None:
        lines.append("  израсходовано:      нет данных")
    else:
        lines.append(f"  израсходовано:      {report.consumed * 100:.1f} % бюджета")
    if report.remaining_minutes is None:
        lines.append("  осталось:           нет данных")
    else:
        lines.append(
            f"  осталось:           {report.remaining_minutes:.1f} мин "
            f"({format_duration(report.remaining_minutes)} "
            f"из {BUDGET_MINUTES} мин)"
        )
    lines.append(f"  режим политики:     {report.state} — {report.mode_description}")
    for label, value in (
        ("1 ч", report.burn_rate_1h),
        ("6 ч", report.burn_rate_6h),
    ):
        shown = "нет данных" if value is None else f"{value:.2f}x"
        lines.append(f"  burn rate {label}:        {shown}")
    lines.append("")
    lines.append(f"Политика: docs/sre/slo.md §7. Код выхода: {report.exit_code}.")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    """Собрать парсер аргументов."""
    parser = argparse.ArgumentParser(
        description="Отчёт по error budget ClicKit Cloud (M8 T4.1).",
    )
    parser.add_argument(
        "--prometheus-url",
        default=None,
        help=(
            "базовый URL Prometheus "
            f"(по умолчанию $CLICKIT_PROMETHEUS_URL или {DEFAULT_URL})"
        ),
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=5.0,
        help="таймаут запроса к Prometheus в секундах (по умолчанию 5)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="печатать машинночитаемый JSON вместо таблицы",
    )
    return parser


def resolve_url(cli_value: str | None) -> str:
    """Разрешить URL Prometheus: аргумент → env → значение по умолчанию."""
    return cli_value or os.environ.get("CLICKIT_PROMETHEUS_URL") or DEFAULT_URL


def main(argv: list[str] | None = None) -> int:
    """Точка входа скрипта.

    Args:
        argv: Аргументы командной строки (по умолчанию `sys.argv[1:]`).

    Returns:
        Код выхода по политике §7 (0/1/2) или 3 — нет данных.
    """
    args = build_parser().parse_args(argv)
    url = resolve_url(args.prometheus_url)
    try:
        report = collect_report(url, timeout=args.timeout)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"Prometheus недоступен ({url}): {exc}", file=sys.stderr)
        print(
            "Поднимите стек: docker compose -f docker-compose.observability.yml up -d",
            file=sys.stderr,
        )
        return EXIT_NO_DATA
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"Некорректный ответ Prometheus: {exc}", file=sys.stderr)
        return EXIT_NO_DATA

    if args.json:
        print(json.dumps(report_as_dict(report), ensure_ascii=False, indent=2))
    else:
        print(format_report(report))
    return report.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
