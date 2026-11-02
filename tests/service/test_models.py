"""Тесты моделей: таблицы, колонки и индексы соответствуют `docs/api.md` §8."""

from __future__ import annotations

import pytest

pytest.importorskip("sqlalchemy")

from sqlalchemy.dialects.postgresql import JSONB  # noqa: E402

from service.app.models import Base, CrashReport, Scenario  # noqa: E402

#: Ожидаемые колонки таблицы сценариев.
SCENARIO_COLUMNS = {
    "id",
    "name",
    "description",
    "ir",
    "sha256",
    "idempotency_key",
    "idempotency_body",
    "created_at",
    "updated_at",
}
#: Ожидаемые колонки crash-отчётов.
CRASH_REPORT_COLUMNS = {
    "id",
    "app_version",
    "os",
    "error_hash",
    "traceback",
    "created_at",
}


def test_metadata_contains_contract_tables() -> None:
    """В metadata ровно две таблицы контракта."""
    assert set(Base.metadata.tables) == {"scenarios", "crash_reports"}


def test_scenario_columns_match_contract() -> None:
    """Набор и типы колонок `scenarios` соответствуют SQL из §8."""
    table = Scenario.__table__

    assert set(table.columns.keys()) == SCENARIO_COLUMNS
    assert isinstance(table.c.ir.type, JSONB)
    assert table.c.sha256.type.length == 64
    assert table.c.idempotency_body.type.length == 64
    assert table.c.created_at.type.timezone is True


def test_crash_report_columns_match_contract() -> None:
    """Набор колонок `crash_reports` соответствует SQL из §8."""
    table = CrashReport.__table__

    assert set(table.columns.keys()) == CRASH_REPORT_COLUMNS
    assert table.c.error_hash.type.length == 64


def test_idempotency_index_is_unique() -> None:
    """Уникальный индекс резервирует `Idempotency-Key` (NULL допускается)."""
    index = next(
        index
        for index in Scenario.__table__.indexes
        if index.name == "ux_scenarios_idempotency_key"
    )

    assert index.unique is True
    assert [column.name for column in index.columns] == ["idempotency_key"]


def test_created_at_index_is_descending() -> None:
    """Список сценариев сортируется по `created_at DESC`."""
    index = next(
        index
        for index in Scenario.__table__.indexes
        if index.name == "ix_scenarios_created_at"
    )
    expression = next(iter(index.expressions))

    assert str(expression).endswith("DESC")


def test_sha256_and_crash_report_indexes_exist() -> None:
    """Индексы скачивания по хэшу и по времени отчётов объявлены."""
    scenario_indexes = {index.name for index in Scenario.__table__.indexes}
    crash_indexes = {index.name for index in CrashReport.__table__.indexes}

    assert "ix_scenarios_sha256" in scenario_indexes
    assert "ix_crash_reports_created_at" in crash_indexes
