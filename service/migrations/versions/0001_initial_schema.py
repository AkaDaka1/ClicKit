"""Начальная схема ClicKit Cloud: сценарии и crash-отчёты.

Схема повторяет `docs/api.md` §8: `scenarios` (IR + хэш + резервация
идемпотентности) и `crash_reports` (без PII). Уникальный индекс по
`idempotency_key` допускает много NULL — так сценарии без ключа не мешают
друг другу.

Revision ID: 0001
Revises:
Create Date: 2026-11-02
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Создать таблицы, ограничения и индексы."""
    op.create_table(
        "scenarios",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "description",
            sa.Text(),
            server_default=sa.text("''"),
            nullable=False,
        ),
        sa.Column(
            "ir",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment="нормализованный IR",
        ),
        sa.Column(
            "sha256",
            sa.CHAR(64),
            nullable=False,
            comment="канонический хэш IR",
        ),
        sa.Column("idempotency_key", sa.Text(), nullable=True),
        sa.Column("idempotency_body", sa.CHAR(64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "char_length(name) BETWEEN 1 AND 200",
            name="ck_scenarios_name_length",
        ),
        sa.CheckConstraint(
            "char_length(description) <= 2000",
            name="ck_scenarios_description_length",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ux_scenarios_idempotency_key",
        "scenarios",
        ["idempotency_key"],
        unique=True,
    )
    op.create_index("ix_scenarios_sha256", "scenarios", ["sha256"])
    op.create_index(
        "ix_scenarios_created_at",
        "scenarios",
        [sa.text("created_at DESC")],
    )

    op.create_table(
        "crash_reports",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("app_version", sa.Text(), nullable=False),
        sa.Column(
            "os",
            sa.Text(),
            server_default=sa.text("''"),
            nullable=False,
        ),
        sa.Column("error_hash", sa.CHAR(64), nullable=False),
        sa.Column(
            "traceback",
            sa.Text(),
            nullable=True,
            comment="санитайзер путей + обрезка до 16 КБ",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "char_length(app_version) BETWEEN 1 AND 64",
            name="ck_crash_reports_app_version_length",
        ),
        sa.CheckConstraint(
            "char_length(os) <= 64",
            name="ck_crash_reports_os_length",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_crash_reports_created_at", "crash_reports", ["created_at"])


def downgrade() -> None:
    """Удалить индексы и таблицы в обратном порядке."""
    op.drop_index("ix_crash_reports_created_at", table_name="crash_reports")
    op.drop_table("crash_reports")
    op.drop_index("ix_scenarios_created_at", table_name="scenarios")
    op.drop_index("ix_scenarios_sha256", table_name="scenarios")
    op.drop_index("ux_scenarios_idempotency_key", table_name="scenarios")
    op.drop_table("scenarios")
