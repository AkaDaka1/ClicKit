"""SQLAlchemy-реализация хранилища сценариев ClicKit Cloud.

Класс `SqlScenarioRepository` реализует `scenario_service.ScenarioRepository`:
владеет одной сессией на запрос, выполняет запросы к таблице `scenarios` и
превращает `IntegrityError` уникального индекса `idempotency_key` в
`ScenarioConflictError` (гонка запросов, `docs/api.md` §7). Бизнес-логика
публикации от SQL не зависят — см. `service/app/scenario_service.py`.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from service.app.models import Scenario
from service.app.scenario_service import (
    ScenarioConflictError,
    ValidatedPublication,
)


class SqlScenarioRepository:
    """Хранилище сценариев поверх одной SQLAlchemy-сессии."""

    def __init__(self, session: Session) -> None:
        """Обернуть открытую сессию SQLAlchemy.

        Args:
            session: Сессия, которую открыл вызывающий код (запрос приложения).
        """
        self._session = session

    def find_by_idempotency_key(self, key: str) -> Scenario | None:
        """Найти строку, резервирующую ключ идемпотентности."""
        statement = select(Scenario).where(Scenario.idempotency_key == key)
        return self._session.execute(statement).scalar_one_or_none()

    def get(self, scenario_id: uuid.UUID) -> Scenario | None:
        """Найти сценарий по идентификатору."""
        return self._session.get(Scenario, scenario_id)

    def create(
        self,
        publication: ValidatedPublication,
        *,
        idempotency_key: str | None,
        idempotency_body: str | None,
    ) -> Scenario:
        """Вставить сценарий; при гонке по ключу — `ScenarioConflictError`."""
        record = Scenario(
            name=publication.name,
            description=publication.description,
            ir=publication.ir,
            sha256=publication.sha256,
            idempotency_key=idempotency_key,
            idempotency_body=idempotency_body if idempotency_key else None,
        )
        self._session.add(record)
        try:
            self._session.flush()
        except IntegrityError as exc:
            self._session.rollback()
            raise ScenarioConflictError(
                "Idempotency-Key уже зарезервирован другим запросом"
            ) from exc
        except SQLAlchemyError as exc:
            self._session.rollback()
            raise RuntimeError("Не удалось сохранить сценарий") from exc
        if record.id is None or record.created_at is None:
            raise RuntimeError("БД не вернула идентификатор или время создания")
        return record

    def clear_idempotency_key(self, record: Scenario) -> None:
        """Снять резервацию с протухшей строки (см. `docs/api.md` §7, п. 5)."""
        record.idempotency_key = None
        record.idempotency_body = None
        self._session.flush()

    def list_page(
        self,
        *,
        limit: int,
        offset: int,
    ) -> tuple[list[Scenario], int]:
        """Вернуть страницу сценариев (`created_at DESC`) и полное число строк."""
        total = int(
            self._session.execute(
                select(func.count()).select_from(Scenario)
            ).scalar_one()
        )
        statement = (
            select(Scenario)
            .order_by(Scenario.created_at.desc(), Scenario.id.desc())
            .limit(limit)
            .offset(offset)
        )
        items = list(self._session.execute(statement).scalars().all())
        return items, total

    def delete(self, record: Scenario) -> None:
        """Пометить сценарий удалённым (фиксация — `commit`)."""
        self._session.delete(record)
        self._session.flush()

    def commit(self) -> None:
        """Зафиксировать транзакцию."""
        self._session.commit()

    def rollback(self) -> None:
        """Откатить транзакцию."""
        self._session.rollback()
