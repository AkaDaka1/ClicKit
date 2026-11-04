"""Общие фикстуры тестов API сценариев ClicKit Cloud.

Каждый тест получает изолированную БД через `DATABASE_FACTORY`: локально это
файловая SQLite (быстро, без инфраструктуры), а в CI-джобе `service-tests`
переменной `CLICKIT_TEST_DB_URL` подключается настоящий PostgreSQL 16 — тогда
те же тесты проверяют уникальный индекс, `JSONB` и `timestamptz` на реальной
СУБД (T5.1). Схема создаётся `Base.metadata` (продакшен — только Alembic).
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Protocol

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("sqlalchemy")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, event, text  # noqa: E402

from service.app.config import Settings  # noqa: E402
from service.app.db import Database  # noqa: E402
from service.app.main import create_app  # noqa: E402
from service.app.models import Base  # noqa: E402

#: Валидный ключ записи для тестов (≥ 16 символов).
API_KEY = "test-key-0123456789"
#: URL БД-заглушки для тестов, которые не пишут в реальную БД.
DB_URL = "postgresql+psycopg://clikit:clikit@localhost:5432/clikit"
#: Пример IR, совпадающий с `resources/examples/click_pause_loop.acl.json`.
SAMPLE_SCENARIO: dict[str, Any] = {
    "version": 1,
    "name": "demo",
    "nodes": [{"type": "click", "x": 100, "y": 200}],
}


class DatabaseFactory(Protocol):
    """Создание изолированной БД с готовой схемой для одного теста."""

    def __call__(self) -> Database:
        """Вернуть БД; освобождение — через `dispose`."""
        ...


class SqliteFactory:
    """Файловая SQLite: быстрая БД по умолчанию для локальных прогонов."""

    def __init__(self, directory: Path) -> None:
        """Запомнить каталог для файлов БД.

        Args:
            directory: Каталог `tmp_path` текущего теста.
        """
        self._directory = directory

    def __call__(self) -> Database:
        """Создать свежий файл SQLite и таблицы из `Base.metadata`."""
        path = self._directory / f"db-{uuid.uuid4().hex}.sqlite"
        database = Database(f"sqlite+pysqlite:///{path.as_posix()}")
        _install_sqlite_shims(database.engine)
        Base.metadata.create_all(database.engine)
        return database


def _install_sqlite_shims(engine: Any) -> None:
    """Добавить SQLite недостающие функции схемы (только для тестов).

    Схема `docs/api.md` §8 использует `char_length` и `gen_random_uuid()`,
    которых нет в SQLite. Схему ради тестов не подменяем, поэтому функции
    регистрируются как UDF SQLite — поведение остаётся близким PostgreSQL.
    """

    @event.listens_for(engine, "connect")
    def _register(dbapi_connection: Any, _record: Any) -> None:
        dbapi_connection.create_function(
            "char_length", 1, lambda value: len(value) if value is not None else None
        )
        dbapi_connection.create_function("gen_random_uuid", 0, lambda: uuid.uuid4().hex)


class PostgresFactory:
    """Постгресовый сервер из env: схема создаётся и удаляется на каждый тест."""

    def __init__(self, url: str) -> None:
        """Запомнить URL сервера.

        Args:
            url: SQLAlchemy URL PostgreSQL (обычно отдельная база под тесты).
        """
        self._url = url

    def __call__(self) -> Database:
        """Создать схему `Base.metadata` в тестовой БД."""
        database = Database(self._url)
        with database.engine.begin() as connection:
            connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            connection.execute(text("CREATE SCHEMA public"))
        Base.metadata.create_all(database.engine)
        return database


@pytest.fixture()
def database_factory(tmp_path: Path) -> DatabaseFactory:
    """Фабрика БД: PostgreSQL из `CLICKIT_TEST_DB_URL` или файловая SQLite."""
    configured = os.environ.get("CLICKIT_TEST_DB_URL", "").strip()
    if configured:
        return PostgresFactory(configured)
    return SqliteFactory(tmp_path)


@pytest.fixture()
def database(database_factory: DatabaseFactory) -> Iterator[Database]:
    """Одна пустая БД на тест."""
    instance = database_factory()
    try:
        yield instance
    finally:
        instance.dispose()


@pytest.fixture()
def client(database: Database) -> Iterator[TestClient]:
    """Клиент приложения с явными настройками и рабочей БД."""
    app = create_app(
        Settings(
            api_key=API_KEY,
            db_url=database.url,
            idempotency_ttl_hours=24,
        ),
        database=database,
    )
    with TestClient(app) as test_client:
        # Публичные GET-методы ключ игнорируют; защищённые POST/DELETE в тестах
        # получают валидный ключ записи по умолчанию (T3.1). Тесты 401/403
        # переопределяют заголовок явно.
        test_client.headers.update({"X-API-Key": API_KEY})
        yield test_client


def publish_body(
    *,
    name: str | None = "demo",
    description: str | None = None,
    scenario: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Собрать тело `POST /v1/scenarios`.

    Args:
        name: Значение поля `name` (по умолчанию `"demo"`).
        description: Значение поля `description` (по умолчанию отсутствует).
        scenario: IR-сценарий (по умолчанию `SAMPLE_SCENARIO`).

    Returns:
        Словарь тела запроса.
    """
    body: dict[str, Any] = {
        "scenario": dict(SAMPLE_SCENARIO) if scenario is None else scenario
    }
    if name is not None:
        body["name"] = name
    if description is not None:
        body["description"] = description
    return body


def create_engine_ping(url: str) -> bool:
    """Проверить, доступна ли БД по URL (для теста на PostgreSQL)."""
    try:
        engine = create_engine(url, connect_args={"connect_timeout": 3})
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        engine.dispose()
    except Exception:
        return False
    return True
