"""Тесты слоя БД: healthcheck, сессии и освобождение соединений.

PostgreSQL для этих тестов не нужен: `check` проверяется на SQLite (тот же
`SELECT 1`) и на заведомо недоступном порту. Настоящая PostgreSQL проверяется
в чекпоинте T1.2 и в CI (T5.1).
"""

from __future__ import annotations

import pytest

pytest.importorskip("sqlalchemy")

from sqlalchemy import create_engine, text  # noqa: E402

from service.app.db import Database  # noqa: E402

#: In-memory SQLite: тот же SQLAlchemy-путь, но без внешней инфраструктуры.
SQLITE_URL = "sqlite+pysqlite:///:memory:"
#: Порт 1 на loopback закрыт — соединение отклоняется сразу.
UNREACHABLE_URL = "postgresql+psycopg://clikit:clikit@127.0.0.1:1/clikit"


def test_check_returns_true_for_working_database() -> None:
    """Рабочая БД отвечает на `SELECT 1`."""
    database = Database(SQLITE_URL)

    assert database.check() is True

    database.dispose()


def test_check_returns_false_when_database_is_unreachable() -> None:
    """Недоступная БД — `False`, исключение наружу не выходит."""
    database = Database(UNREACHABLE_URL)

    assert database.check() is False

    database.dispose()


def test_engine_is_created_lazily() -> None:
    """Создание `Database` не подключается к БД (сервис стартует без неё)."""
    database = Database(UNREACHABLE_URL)

    assert database.engine.url.get_backend_name() == "postgresql"

    database.dispose()


def test_injected_engine_is_used() -> None:
    """Готовый engine (тесты) не подменяется новым."""
    engine = create_engine(SQLITE_URL)
    database = Database(SQLITE_URL, engine=engine)

    assert database.engine is engine

    database.dispose()


def test_session_returns_working_session() -> None:
    """`session()` отдаёт новую сессию SQLAlchemy (основа CRUD в T2.1)."""
    database = Database(SQLITE_URL)

    with database.session() as session:
        assert session.execute(text("SELECT 1")).scalar_one() == 1

    database.dispose()


def test_session_scope_commits_changes() -> None:
    """Успешный блок `session_scope` фиксирует изменения."""
    database = Database(SQLITE_URL)
    with database.session_scope() as session:
        session.execute(text("CREATE TABLE items (id INTEGER PRIMARY KEY)"))

    with database.session_scope() as session:
        session.execute(text("INSERT INTO items (id) VALUES (1)"))

    with database.session_scope() as session:
        total = session.execute(text("SELECT count(*) FROM items")).scalar_one()
    assert total == 1

    database.dispose()


def test_session_scope_rolls_back_on_error() -> None:
    """Исключение внутри блока откатывает изменения и пробрасывается."""
    database = Database(SQLITE_URL)
    with database.session_scope() as session:
        session.execute(text("CREATE TABLE items (id INTEGER PRIMARY KEY)"))

    with pytest.raises(RuntimeError, match="сбой"):
        with database.session_scope() as session:
            session.execute(text("INSERT INTO items (id) VALUES (1)"))
            raise RuntimeError("сбой")

    with database.session_scope() as session:
        total = session.execute(text("SELECT count(*) FROM items")).scalar_one()
    assert total == 0

    database.dispose()
