"""Статические проверки runbook и постмортемов (M8 T3.2).

Runbook — рабочая инструкция на момент инцидента, поэтому он привязан к
именам алертов из `observability/prometheus/alerts.yml`: переименование
алерта без правки сценария оставляло бы оператора без инструкции. Реальный
постмортем — исторический документ, но и у него проверяются факты (ссылки на
прогоны CI, коммиты, машинные ошибки) и обязательное «действие → владелец →
срок», иначе «разбор» превращается в пересказ.

Формат проверок — дешёвые инварианты без запуска контейнеров; живой чекпоинт
T3.2 — демо «сломай и почини» в T5.1 и chaos-учения M11.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SRE = ROOT / "docs" / "sre"
RUNBOOK = SRE / "runbook.md"
TEMPLATE = SRE / "postmortem-template.md"
POSTMORTEMS = SRE / "postmortems"
REAL_POSTMORTEM = POSTMORTEMS / "2026-10-29-release-pipeline.md"
ALERTS = ROOT / "observability" / "prometheus" / "alerts.yml"
SLO_DOC = SRE / "slo.md"
OBSERVABILITY_DOC = ROOT / "docs" / "observability.md"
CLOUD_DOC = ROOT / "docs" / "cloud.md"

#: Минимум сценариев по критерию готовности M8 §2.
MIN_SCENARIOS = 5

_LINK = re.compile(r"\]\(([^)#\s]+)(?:#[^)]*)?\)")
_SECTION = re.compile(r"^## (\d+)\. ", re.MULTILINE)
_POSTMORTEM_ROW = re.compile(r"^\| A\d+ \|", re.MULTILINE)


def _text(path: Path) -> str:
    """Прочитать файл репозитория в UTF-8."""
    return path.read_text(encoding="utf-8")


def _alert_names() -> set[str]:
    """Имена алертов из правил Prometheus."""
    data = yaml.safe_load(_text(ALERTS))
    return {rule["alert"] for group in data["groups"] for rule in group["rules"]}


def _relative_links(path: Path) -> list[str]:
    """Относительные ссылки документа (без якорей и внешних URL)."""
    links = []
    for target in _LINK.findall(_text(path)):
        if target.startswith(("http://", "https://", "mailto:")):
            continue
        links.append(target)
    return links


def _scenario_sections(text: str) -> dict[int, str]:
    """Разделы-сценарии: `## N.` с N ≥ 3 (до них идут правила и индекс)."""
    parts = _SECTION.split(text)
    sections: dict[int, str] = {}
    for number, body in zip(parts[1::2], parts[2::2], strict=False):
        if int(number) >= 3:
            sections[int(number)] = body
    return sections


def test_runbook_covers_every_alert() -> None:
    """У каждого алерта из правил есть сценарий, а не только строка индекса."""
    sections = _scenario_sections(_text(RUNBOOK))
    for name in sorted(_alert_names()):
        assert any(name in body for body in sections.values()), (
            f"в docs/sre/runbook.md нет сценария для {name}"
        )


def test_runbook_has_enough_actionable_scenarios() -> None:
    """Сценариев не меньше пяти, и у каждого есть признаки и шаги реакции."""
    text = _text(RUNBOOK)
    sections = _scenario_sections(text)
    assert len(sections) >= MIN_SCENARIOS, f"сценариев: {len(sections)}"
    actionable = [
        body
        for body in sections.values()
        if "**Признаки.**" in body or "Отдельного алерта" in body
    ]
    assert len(actionable) >= MIN_SCENARIOS
    assert text.count("**Восстановление.**") >= MIN_SCENARIOS
    # Команды должны быть копируемыми: стек вызывается с явным файлом.
    assert "-f docker-compose.observability.yml" in text
    assert "Первые 3 минуты" in text


def test_runbook_links_resolve() -> None:
    """Относительные ссылки runbook и шаблона не битые."""
    for path in (RUNBOOK, TEMPLATE):
        for target in _relative_links(path):
            assert (path.parent / target).resolve().exists(), (
                f"{path.name}: нет {target}"
            )


def test_postmortem_template_is_blameless_and_complete() -> None:
    """Шаблон содержит обязательные разделы и явно требует blameless-подход."""
    text = _text(TEMPLATE)
    for fragment in (
        "Blameless",
        "Метаданные",
        "Таймлайн",
        "Влияние",
        "Причины",
        "Действия",
        "Уроки",
        "Чек-лист завершения",
        "UTC",
    ):
        assert fragment in text, f"в шаблоне нет раздела/требования {fragment!r}"
    # Действия без владельца и срока не считаются выполненными.
    assert "владелец" in text.lower()
    assert "срок" in text.lower()


def test_real_postmortem_records_the_incident_facts() -> None:
    """Реальный постмортем ссылается на прогоны, коммиты и машинные ошибки."""
    text = _text(REAL_POSTMORTEM)
    for run_id in (
        "40934061829",
        "40934279478",
        "40936253756",
        "40937694525",
        "40944319704",
    ):
        assert run_id in text, f"нет ссылки на прогон {run_id}"
    for commit in ("33186db", "02d873c", "c54db02"):
        assert commit in text, f"нет коммита {commit}"
    assert "нет файла: dist\\NOTICE.txt" in text
    assert "no matches found for" in text
    assert "2026-10-29" in text
    assert "UTC" in text


def test_real_postmortem_actions_have_owner_and_status() -> None:
    """Каждое действие разбора имеет владельца и явный статус."""
    text = _text(REAL_POSTMORTEM)
    rows = _POSTMORTEM_ROW.findall(text)
    assert len(rows) >= 3, "в постмортеме нет таблицы действий"
    for row in text.splitlines():
        if not _POSTMORTEM_ROW.match(row):
            continue
        assert "Danil Momot" in row, f"без владельца: {row[:60]}"
        assert "✅" in row or "⬜" in row, f"без статуса: {row[:60]}"


def test_sre_documents_are_cross_linked() -> None:
    """SLO, стек наблюдаемости и Cloud ссылаются на runbook."""
    for path in (SLO_DOC, OBSERVABILITY_DOC, CLOUD_DOC):
        assert "runbook.md" in _text(path), f"{path.name} не ссылается на runbook"
    assert "postmortem-template.md" in _text(SLO_DOC)
    assert "postmortems/2026-10-29-release-pipeline.md" in _text(RUNBOOK)


def test_sre_documents_have_no_secrets() -> None:
    """В инструкциях и разборах нет ключей и паролей."""
    for path in (RUNBOOK, TEMPLATE, REAL_POSTMORTEM):
        text = _text(path)
        for marker in ("CLICKIT_API_KEY=", "POSTGRES_PASSWORD=", "X-API-Key:"):
            assert marker not in text, f"{path.name}: похоже на секрет ({marker})"


def test_postmortems_directory_has_the_reviewed_incident() -> None:
    """Каталог разборов существует и содержит проверяемый постмортем."""
    assert POSTMORTEMS.is_dir()
    files = sorted(path.name for path in POSTMORTEMS.glob("*.md"))
    assert "2026-10-29-release-pipeline.md" in files
