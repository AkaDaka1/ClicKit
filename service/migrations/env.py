"""Окружение Alembic ClicKit Cloud.

URL БД берётся только из `CLICKIT_DB_URL` (как и у сервиса), секретов в
`alembic.ini` нет. Metadata — модели `service/app/models.py`; изменения схемы
сравниваются с ними при `alembic revision --autogenerate`.
"""

from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Корень репозитория в sys.path: service/migrations/env.py → repo root.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from service.app.models import Base  # noqa: E402

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def database_url() -> str:
    """Прочитать URL БД из окружения с понятной ошибкой.

    Returns:
        SQLAlchemy URL PostgreSQL.

    Raises:
        RuntimeError: `CLICKIT_DB_URL` не задан — миграции некуда применять.
    """
    url = os.environ.get("CLICKIT_DB_URL", "").strip()
    if not url:
        raise RuntimeError(
            "CLICKIT_DB_URL не задан: укажите SQLAlchemy URL PostgreSQL "
            "(см. docs/api.md §9)"
        )
    return url


def run_migrations_offline() -> None:
    """Сгенерировать SQL без подключения к БД (`alembic upgrade --sql`)."""
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Применить миграции к БД из `CLICKIT_DB_URL`."""
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = database_url()
    connectable = engine_from_config(
        configuration, prefix="sqlalchemy.", poolclass=pool.NullPool
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
