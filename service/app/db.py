"""Подключение сервиса ClicKit Cloud к PostgreSQL.

Модуль отвечает только за engine, фабрику сессий и healthcheck. Модели живут
в `service/app/models.py`, схема БД описана в `docs/api.md` §8, а изменения
схемы применяются исключительно миграциями Alembic (`service/migrations`).
Engine создаётся в `lifespan` приложения, поэтому импорт модуля не требует
ни окружения, ни запущенной БД.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Protocol

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)

#: Проверка доступности БД: дешёвый запрос, не затрагивающий данные.
HEALTHCHECK_SQL = "SELECT 1"
#: Таймаут установки соединения, секунды: `/readyz` не должен висеть минутами.
DB_CONNECT_TIMEOUT_SECONDS = 5


class DatabaseProtocol(Protocol):
    """Минимальный интерфейс БД, нужный приложению (в тестах — подделка)."""

    def check(self) -> bool:
        """Проверить доступность БД."""
        ...

    def dispose(self) -> None:
        """Освободить соединения."""
        ...


class Database:
    """Engine PostgreSQL, фабрика сессий и проверка доступности для `/readyz`."""

    def __init__(self, url: str, *, engine: Engine | None = None) -> None:
        """Создать подключение по SQLAlchemy URL.

        Args:
            url: SQLAlchemy URL из `CLICKIT_DB_URL` (`docs/api.md` §9).
            engine: Готовый engine (тесты); `None` — создать по умолчанию.
        """
        self.url = url
        if engine is None:
            engine = self._create_engine(url)
        self._engine = engine
        self._session_factory = sessionmaker(
            bind=self._engine, expire_on_commit=False, future=True
        )

    @staticmethod
    def _create_engine(url: str) -> Engine:
        """Создать engine; для PostgreSQL задать короткий таймаут соединения."""
        if url.startswith(("postgresql", "postgres")):
            return create_engine(
                url,
                pool_pre_ping=True,
                future=True,
                connect_args={"connect_timeout": DB_CONNECT_TIMEOUT_SECONDS},
            )
        return create_engine(url, pool_pre_ping=True, future=True)

    @property
    def engine(self) -> Engine:
        """Engine SQLAlchemy (используется миграциями и тестами)."""
        return self._engine

    def session(self) -> Session:
        """Открыть новую сессию; закрывать её обязан вызывающий код."""
        return self._session_factory()

    @contextmanager
    def session_scope(self) -> Iterator[Session]:
        """Сессия с фиксацией при успехе и откатом при исключении."""
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def check(self) -> bool:
        """Выполнить `SELECT 1` и сообщить, доступна ли БД.

        Ошибки подключения не пробрасываются: `/readyz` отвечает 503, а
        подробности попадают только в журнал (в ответе их нет, `docs/api.md`
        §5.2).

        Returns:
            `True`, если БД ответила на простой запрос, иначе `False`.
        """
        try:
            with self._engine.connect() as connection:
                connection.execute(text(HEALTHCHECK_SQL))
        except SQLAlchemyError as exc:
            logger.warning("Проверка БД не прошла: %s", exc)
            return False
        return True

    def dispose(self) -> None:
        """Закрыть пул соединений при остановке сервиса."""
        self._engine.dispose()
        logger.debug("Соединения с БД закрыты")
