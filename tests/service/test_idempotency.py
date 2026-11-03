"""Тесты идемпотентности `POST /v1/scenarios` (`docs/api.md` §7).

Семантика контракта: без ключа — обычное создание; тот же ключ и то же тело —
replay с заголовком `Idempotent-Replay`; то же ключ и другое тело — 409;
протухшая резервация снимается в той же транзакции, а гонка двух запросов
разрешается уникальным индексом, а не 500.
"""

from __future__ import annotations

import threading
import uuid
from datetime import UTC, datetime, timedelta

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("sqlalchemy")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select, update  # noqa: E402

from service.app.models import Scenario  # noqa: E402
from service.app.scenario_service import (  # noqa: E402
    ScenarioConflictError,
    build_publication,
    publish,
    request_body_hash,
)
from tests.service.conftest import publish_body  # noqa: E402

#: Валидный `Idempotency-Key`.
KEY = "publish-demo-0001"


def test_same_key_same_body_is_replay(client: TestClient) -> None:
    """Повтор с тем же телом не создаёт дубль и помечается replay (§7, п. 3)."""
    first = client.post(
        "/v1/scenarios", json=publish_body(), headers={"Idempotency-Key": KEY}
    )
    second = client.post(
        "/v1/scenarios", json=publish_body(), headers={"Idempotency-Key": KEY}
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.headers["idempotent-replay"] == "true"
    assert second.json() == first.json()
    assert client.get("/v1/scenarios").json()["total"] == 1
    assert first.headers.get("idempotent-replay") is None


def test_same_key_different_body_is_409(client: TestClient) -> None:
    """Тот же ключ с другим телом — 409 conflict (§7, п. 4)."""
    client.post("/v1/scenarios", json=publish_body(), headers={"Idempotency-Key": KEY})

    response = client.post(
        "/v1/scenarios",
        json=publish_body(name="other"),
        headers={"Idempotency-Key": KEY},
    )

    assert response.status_code == 409
    assert response.json()["type"] == "urn:clikit:error:conflict"
    assert client.get("/v1/scenarios").json()["total"] == 1


def test_different_keys_create_different_rows(client: TestClient) -> None:
    """Разные ключи — разные сценарии."""
    first = client.post(
        "/v1/scenarios", json=publish_body(), headers={"Idempotency-Key": KEY}
    ).json()
    second = client.post(
        "/v1/scenarios", json=publish_body(), headers={"Idempotency-Key": f"{KEY}-2"}
    ).json()

    assert second["id"] != first["id"]
    assert client.get("/v1/scenarios").json()["total"] == 2


def test_without_key_duplicates_are_allowed(client: TestClient) -> None:
    """Без ключа дубликаты разрешены (§7, п. 1)."""
    client.post("/v1/scenarios", json=publish_body())
    client.post("/v1/scenarios", json=publish_body())

    assert client.get("/v1/scenarios").json()["total"] == 2


def test_too_short_key_is_422(client: TestClient) -> None:
    """Ключ короче 8 символов — 422."""
    response = client.post(
        "/v1/scenarios", json=publish_body(), headers={"Idempotency-Key": "short"}
    )

    assert response.status_code == 422
    assert response.json()["errors"][0]["path"] == "Idempotency-Key"


def test_illegal_characters_in_key_are_422(client: TestClient) -> None:
    """Символы вне `[A-Za-z0-9._:-]` — 422."""
    response = client.post(
        "/v1/scenarios",
        json=publish_body(),
        headers={"Idempotency-Key": "key with space"},
    )

    assert response.status_code == 422


def test_key_too_long_is_422(client: TestClient) -> None:
    """Ключ длиннее 128 символов — 422."""
    response = client.post(
        "/v1/scenarios", json=publish_body(), headers={"Idempotency-Key": "k" * 129}
    )

    assert response.status_code == 422


def test_expired_reservation_is_reclaimed(client: TestClient, database) -> None:
    """Протухшая резервация снимается и ключ переиспользуется (§7, п. 5)."""
    first = client.post(
        "/v1/scenarios", json=publish_body(), headers={"Idempotency-Key": KEY}
    ).json()
    stale = datetime.now(UTC) - timedelta(hours=25)
    with database.session_scope() as session:
        session.execute(
            update(Scenario)
            .where(Scenario.id == uuid.UUID(first["id"]))
            .values(created_at=stale)
        )

    second = client.post(
        "/v1/scenarios",
        json=publish_body(name="fresh"),
        headers={"Idempotency-Key": KEY},
    )

    assert second.status_code == 201
    assert second.json()["id"] != first["id"]
    with database.session_scope() as session:
        rows = session.execute(select(Scenario)).scalars().all()
    reserved = [row for row in rows if row.idempotency_key == KEY]
    assert len(reserved) == 1
    assert reserved[0].name == "fresh"


def test_fresh_reservation_with_other_body_conflicts(client: TestClient) -> None:
    """Свежая резервация с другим телом — 409, даже если прошло много попыток."""
    client.post("/v1/scenarios", json=publish_body(), headers={"Idempotency-Key": KEY})

    for _ in range(2):
        response = client.post(
            "/v1/scenarios",
            json=publish_body(description="иное"),
            headers={"Idempotency-Key": KEY},
        )
        assert response.status_code == 409


class _InMemoryRepository:
    """Подделка хранилища: резервирует ключ и считает вызовы `create`."""

    def __init__(self, *, fail_once: bool = False) -> None:
        """Настроить подделку.

        Args:
            fail_once: Сымитировать гонку — первый `create` падает конфликтом,
                хотя строка уже «существует» (как при параллельном запросе).
        """
        self.records: list[Scenario] = []
        self.fail_once = fail_once
        self.created = 0
        self._tick = 0

    def _next_time(self) -> datetime:
        self._tick += 1
        return datetime.now(UTC) + timedelta(seconds=self._tick)

    def get(self, scenario_id):  # noqa: ANN001, ANN201 - протокол тестов
        return next((r for r in self.records if r.id == scenario_id), None)

    def find_by_idempotency_key(self, key: str) -> Scenario | None:
        return next((r for r in self.records if r.idempotency_key == key), None)

    def create(self, publication, *, idempotency_key, idempotency_body):  # noqa: ANN001, ANN201
        if self.fail_once:
            self.fail_once = False
            existing = self.find_by_idempotency_key(idempotency_key or "")
            if existing is not None:
                raise ScenarioConflictError("гонка")
        record = Scenario(
            name=publication.name,
            description=publication.description,
            ir=publication.ir,
            sha256=publication.sha256,
            idempotency_key=idempotency_key,
            idempotency_body=idempotency_body,
            created_at=self._next_time(),
            updated_at=self._next_time(),
        )
        import uuid

        record.id = uuid.uuid4()
        self.records.append(record)
        self.created += 1
        return record

    def clear_idempotency_key(self, record: Scenario) -> None:
        record.idempotency_key = None
        record.idempotency_body = None

    def list_page(self, *, limit: int, offset: int):
        return self.records[offset : offset + limit], len(self.records)

    def delete(self, record: Scenario) -> None:
        self.records.remove(record)

    def commit(self) -> None:
        pass

    def rollback(self) -> None:
        pass


def _publication(name: str = "demo"):
    return build_publication(
        name=name,
        description=None,
        scenario={
            "version": 1,
            "name": "demo",
            "nodes": [{"type": "click", "x": 1, "y": 1}],
        },
    )


def test_publish_without_key_creates_each_time() -> None:
    """Без ключа `publish` создаёт строку при каждом вызове."""
    repository = _InMemoryRepository()
    body_hash = request_body_hash({"name": "demo"})

    publish(
        repository,
        _publication(),
        idempotency_key=None,
        idempotency_body=body_hash,
        ttl_hours=24,
    )
    _, replay = publish(
        repository,
        _publication(),
        idempotency_key=None,
        idempotency_body=body_hash,
        ttl_hours=24,
    )

    assert replay is False
    assert repository.created == 2


def test_race_resolved_as_replay() -> None:
    """Гонка: второй запрос видит конфликт индекса и возвращает replay."""
    repository = _InMemoryRepository()
    body_hash = request_body_hash({"name": "demo"})
    publish(
        repository,
        _publication(),
        idempotency_key=KEY,
        idempotency_body=body_hash,
        ttl_hours=24,
    )

    repository.fail_once = True
    record, replay = publish(
        repository,
        _publication(),
        idempotency_key=KEY,
        idempotency_body=body_hash,
        ttl_hours=24,
    )

    assert replay is True
    assert repository.created == 1
    assert record.idempotency_key == KEY


def test_race_with_other_body_is_conflict() -> None:
    """Гонка с другим телом — `ScenarioConflictError`, а не 500."""
    repository = _InMemoryRepository()
    first_hash = request_body_hash({"name": "demo"})
    publish(
        repository,
        _publication(),
        idempotency_key=KEY,
        idempotency_body=first_hash,
        ttl_hours=24,
    )

    repository.fail_once = True
    with pytest.raises(ScenarioConflictError):
        publish(
            repository,
            _publication("other"),
            idempotency_key=KEY,
            idempotency_body=request_body_hash({"name": "other"}),
            ttl_hours=24,
        )


def test_concurrent_requests_with_same_key_create_one_row(
    database,
) -> None:
    """Параллельные запросы с одним ключом дают одну строку и replay."""
    publication = _publication()
    body_hash = request_body_hash({"name": "demo"})
    results: list[tuple[str, bool]] = []
    errors: list[BaseException] = []
    barrier = threading.Barrier(2)

    def worker() -> None:
        from service.app.repository import SqlScenarioRepository

        session = database.session()
        try:
            barrier.wait(timeout=10)
            record, replay = publish(
                SqlScenarioRepository(session),
                publication,
                idempotency_key=KEY,
                idempotency_body=body_hash,
                ttl_hours=24,
            )
            results.append((str(record.id), replay))
        except BaseException as exc:  # noqa: BLE001 - собрать для диагностики
            errors.append(exc)
        finally:
            session.close()

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)

    failures = [
        error for error in errors if not isinstance(error, ScenarioConflictError)
    ]
    assert not failures
    with database.session_scope() as session:
        rows = (
            session.execute(select(Scenario).where(Scenario.idempotency_key == KEY))
            .scalars()
            .all()
        )
    assert len(rows) == 1
    assert len(results) + len(errors) == 2
