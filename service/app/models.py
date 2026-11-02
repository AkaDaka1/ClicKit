"""SQLAlchemy-модели ClicKit Cloud.

Нормативная схема — `docs/api.md` §8; расхождение модели и миграции считается
багом, а не «особенностью». Модели описывают таблицы, но ничего не создают:
DDL применяется только Alembic (`service/migrations`), поэтому запуск сервиса
не меняет схему БД молча.

Имена и ограничения намеренно повторяют SQL из контракта: `char(64)` у хэшей,
`jsonb` у IR, `timestamptz` у времени, CHECK на длины строк.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CHAR,
    CheckConstraint,
    DateTime,
    Index,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Базовый класс моделей: `Base.metadata` — источник для Alembic."""


class Scenario(Base):
    """Опубликованный сценарий: метаданные, нормализованный IR и его хэш."""

    __tablename__ = "scenarios"
    __table_args__ = (
        CheckConstraint(
            "char_length(name) BETWEEN 1 AND 200",
            name="ck_scenarios_name_length",
        ),
        CheckConstraint(
            "char_length(description) <= 2000",
            name="ck_scenarios_description_length",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("''")
    )
    ir: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, comment="нормализованный IR"
    )
    sha256: Mapped[str] = mapped_column(
        CHAR(64), nullable=False, comment="канонический хэш IR"
    )
    idempotency_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_body: Mapped[str | None] = mapped_column(CHAR(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class CrashReport(Base):
    """Отчёт о падении desktop-приложения (без PII и IP)."""

    __tablename__ = "crash_reports"
    __table_args__ = (
        CheckConstraint(
            "char_length(app_version) BETWEEN 1 AND 64",
            name="ck_crash_reports_app_version_length",
        ),
        CheckConstraint(
            "char_length(os) <= 64",
            name="ck_crash_reports_os_length",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    app_version: Mapped[str] = mapped_column(Text, nullable=False)
    os: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    error_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    traceback: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="санитайзер путей + обрезка до 16 КБ"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


# Индексы объявлены после классов: для DESC-индекса нужен объект колонки.
# Уникальный индекс допускает много NULL (семантика Postgres) — это и нужно:
# у сценариев без `Idempotency-Key` ключ не зарезервирован.
Index("ux_scenarios_idempotency_key", Scenario.idempotency_key, unique=True)
Index("ix_scenarios_sha256", Scenario.sha256)
Index("ix_scenarios_created_at", Scenario.created_at.desc())
Index("ix_crash_reports_created_at", CrashReport.created_at)
