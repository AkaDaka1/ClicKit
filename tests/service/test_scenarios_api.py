"""Тесты CRUD сценариев ClicKit Cloud (`/v1/scenarios`).

Проверяется контракт `docs/api.md` §5.5–5.8: публикация 201, скачивание 200
с `ETag` и 304, список с пагинацией, удаление 204 и 404, ошибки 413/415/422
в формате problem+json. БД подставляется фикстурой `database` (SQLite или
PostgreSQL из `CLICKIT_TEST_DB_URL`).
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("sqlalchemy")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import update  # noqa: E402

from service.app.models import Scenario  # noqa: E402
from service.app.scenario_service import (  # noqa: E402
    canonical_scenario_hash,
    request_body_hash,
)
from tests.service.conftest import (  # noqa: E402
    API_KEY,
    SAMPLE_SCENARIO,
    publish_body,
)

#: Валидный `Idempotency-Key` (8–128 символов `[A-Za-z0-9._:-]`).
IDEMPOTENCY_KEY = "publish-demo-0001"


def test_publish_returns_201_with_metadata(client: TestClient) -> None:
    """Публикация отдаёт 201, метаданные и ссылку скачивания (§5.5)."""
    response = client.post("/v1/scenarios", json=publish_body())

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "demo"
    assert body["description"] == ""
    assert len(body["sha256"]) == 64
    assert body["url"] == f"/v1/scenarios/{body['id']}"
    assert response.headers["location"] == body["url"]
    assert body["created_at"].endswith("Z")
    assert body["updated_at"].endswith("Z")


def test_publish_normalizes_ir_with_canonical_hash(client: TestClient) -> None:
    """`sha256` — хэш нормализованного IR, а не исходного тела."""
    raw = {
        "version": 1,
        "name": "demo",
        "nodes": [{"type": "click", "x": 100, "y": 200}],
        "unknown_key": "игнорируется",
    }
    response = client.post("/v1/scenarios", json=publish_body(scenario=raw))

    assert response.status_code == 201
    normalized = {
        "version": 1,
        "name": "demo",
        "nodes": [{"type": "click", "x": 100, "y": 200, "button": "left"}],
    }
    assert response.json()["sha256"] == canonical_scenario_hash(normalized)


def test_name_falls_back_to_scenario_name(client: TestClient) -> None:
    """Без `name` в теле имя берётся из IR (§5.5)."""
    response = client.post("/v1/scenarios", json=publish_body(name=None))

    assert response.status_code == 201
    assert response.json()["name"] == "demo"


def test_description_is_saved_and_trimmed_from_name(client: TestClient) -> None:
    """Описание сохраняется, имя без крайних пробелов."""
    response = client.post(
        "/v1/scenarios",
        json=publish_body(name="  spaced  ", description="пример"),
    )

    assert response.status_code == 201
    assert response.json()["name"] == "spaced"
    assert response.json()["description"] == "пример"


def test_missing_name_everywhere_is_422(client: TestClient) -> None:
    """Ни в теле, ни в IR нет имени — 422 с путём `name`."""
    scenario = {"version": 1, "nodes": [{"type": "click", "x": 1, "y": 1}]}
    response = client.post(
        "/v1/scenarios", json=publish_body(name=None, scenario=scenario)
    )

    assert response.status_code == 422
    body = response.json()
    assert body["type"] == "urn:clikit:error:validation"
    assert body["errors"] == [
        {"path": "name", "message": "укажите name или непустое имя в scenario"}
    ]


def test_invalid_ir_returns_422_with_paths(client: TestClient) -> None:
    """Ошибки IR приходят путями `core.ir.schema`, а не 500 (§4, §6)."""
    scenario = {
        "version": 1,
        "name": "bad",
        "nodes": [{"type": "click", "x": 100}, {"type": "teleport"}],
    }
    response = client.post("/v1/scenarios", json=publish_body(scenario=scenario))

    assert response.status_code == 422
    errors = response.json()["errors"]
    paths = {error["path"] for error in errors}
    assert "nodes[0].y" in paths
    assert "nodes[1]" in paths


def test_non_object_scenario_is_422(client: TestClient) -> None:
    """`scenario` не объект — 422 с путём `scenario`."""
    response = client.post("/v1/scenarios", json=publish_body(scenario=["x"]))

    assert response.status_code == 422
    assert response.json()["errors"][0]["path"] == "scenario"


def test_non_object_body_is_422(client: TestClient) -> None:
    """Тело-массив вместо объекта — 422 с путём `$`."""
    response = client.post("/v1/scenarios", json=[1, 2, 3])

    assert response.status_code == 422
    assert response.json()["errors"][0]["path"] == "$"


def test_payload_too_large_is_413(client: TestClient) -> None:
    """Тело больше 1 МБ отклоняется до разбора (§4, §6)."""
    huge = "x" * (1_048_576 + 10)
    response = client.post(
        "/v1/scenarios",
        content=json.dumps(publish_body(description=huge)),
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 413
    assert response.json()["type"] == "urn:clikit:error:payload-too-large"


def test_wrong_content_type_is_415(client: TestClient) -> None:
    """`Content-Type` не JSON — 415 (§4)."""
    response = client.post(
        "/v1/scenarios", content=b"{}", headers={"Content-Type": "text/plain"}
    )

    assert response.status_code == 415
    assert response.json()["type"] == "urn:clikit:error:unsupported-media-type"


def test_malformed_json_is_422(client: TestClient) -> None:
    """Битый JSON — 422, а не 500."""
    response = client.post(
        "/v1/scenarios",
        content=b'{"name": ',
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 422
    assert response.json()["errors"][0]["path"] == "$"


def test_unknown_field_in_body_is_ignored(client: TestClient) -> None:
    """Неизвестные поля тела не ломают публикацию (§1)."""
    body = publish_body()
    body["extra"] = {"anything": True}

    response = client.post("/v1/scenarios", json=body)

    assert response.status_code == 201


def test_download_returns_document_with_etag(client: TestClient) -> None:
    """Скачивание отдаёт полный IR, `ETag` и имя файла (§5.6)."""
    created = client.post("/v1/scenarios", json=publish_body()).json()

    response = client.get(f"/v1/scenarios/{created['id']}")

    assert response.status_code == 200
    assert response.json()["nodes"] == [
        {"type": "click", "x": 100, "y": 200, "button": "left"}
    ]
    assert response.headers["etag"] == f'"{created["sha256"]}"'
    assert 'filename="demo.acl.json"' in response.headers["content-disposition"]


def test_download_with_matching_etag_returns_304(client: TestClient) -> None:
    """`If-None-Match` с текущим `ETag` — 304 без тела (§5.6)."""
    created = client.post("/v1/scenarios", json=publish_body()).json()

    response = client.get(
        f"/v1/scenarios/{created['id']}",
        headers={"If-None-Match": f'"{created["sha256"]}"'},
    )

    assert response.status_code == 304
    assert response.content == b""


def test_download_with_star_etag_returns_304(client: TestClient) -> None:
    """`If-None-Match: *` соответствует любому документу."""
    created = client.post("/v1/scenarios", json=publish_body()).json()

    response = client.get(
        f"/v1/scenarios/{created['id']}", headers={"If-None-Match": "*"}
    )

    assert response.status_code == 304


def test_download_with_weak_etag_returns_304(client: TestClient) -> None:
    """Слабый валидатор `W/"…"` совпадает: для GET сравнение слабое (RFC 9110)."""
    created = client.post("/v1/scenarios", json=publish_body()).json()

    response = client.get(
        f"/v1/scenarios/{created['id']}",
        headers={"If-None-Match": f'W/"{created["sha256"]}"'},
    )

    assert response.status_code == 304


def test_download_with_other_etag_returns_200(client: TestClient) -> None:
    """Чужой `ETag` не совпадает — документ отдаётся целиком."""
    created = client.post("/v1/scenarios", json=publish_body()).json()

    response = client.get(
        f"/v1/scenarios/{created['id']}",
        headers={"If-None-Match": f'"{"0" * 64}"'},
    )

    assert response.status_code == 200


def test_download_unknown_id_is_404(client: TestClient) -> None:
    """Неизвестный id — 404 в problem+json (§4)."""
    response = client.get("/v1/scenarios/00000000-0000-4000-8000-000000000000")

    assert response.status_code == 404
    body = response.json()
    assert body["type"] == "urn:clikit:error:not-found"
    assert body["status"] == 404


def test_download_invalid_uuid_is_422(client: TestClient) -> None:
    """Невалидный UUID в пути — 422 (§5.6)."""
    response = client.get("/v1/scenarios/not-a-uuid")

    assert response.status_code == 422
    assert response.json()["errors"][0]["path"] == "scenario_id"


def test_download_filename_is_sanitized(client: TestClient) -> None:
    """Управляющие символы и кавычки в имени не ломают заголовок (§5.6)."""
    created = client.post(
        "/v1/scenarios",
        json=publish_body(name='клик "запрос"\r\npath/../x'),
    ).json()

    response = client.get(f"/v1/scenarios/{created['id']}")

    disposition = response.headers["content-disposition"]
    assert "\r" not in disposition
    assert "\n" not in disposition
    assert ".." not in disposition
    assert '"клик' not in disposition


def test_list_returns_metadata_without_ir(client: TestClient) -> None:
    """Список отдаёт метаданные без полного IR и полное `total` (§5.7)."""
    for index in range(3):
        client.post("/v1/scenarios", json=publish_body(name=f"scenario-{index}"))

    response = client.get("/v1/scenarios?limit=2&offset=0")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert body["limit"] == 2
    assert body["offset"] == 0
    assert len(body["items"]) == 2
    assert "nodes" not in body["items"][0]


def test_list_is_sorted_newest_first(client: TestClient, database) -> None:
    """Сортировка по `created_at` DESC: новые сверху.

    Время задаётся явно: серверное значение `CURRENT_TIMESTAMP` в SQLite
    имеет точность до секунды, и три записи за одну секунду дали бы
    неотличимый порядок (в PostgreSQL точность микросекундная).
    """
    names = ["first", "second", "third"]
    created = []
    for name in names:
        created.append(
            client.post("/v1/scenarios", json=publish_body(name=name)).json()
        )

    base = datetime.now(UTC).replace(microsecond=0)
    with database.session_scope() as session:
        for index, item in enumerate(created):
            session.execute(
                update(Scenario)
                .where(Scenario.id == uuid.UUID(item["id"]))
                .values(created_at=base + timedelta(seconds=index))
            )

    items = client.get("/v1/scenarios").json()["items"]

    assert [item["name"] for item in items] == ["third", "second", "first"]


def test_list_limit_out_of_range_is_422(client: TestClient) -> None:
    """`limit` вне 1–100 отклоняется FastAPI (422)."""
    assert client.get("/v1/scenarios?limit=0").status_code == 422
    assert client.get("/v1/scenarios?limit=101").status_code == 422


def test_list_negative_offset_is_422(client: TestClient) -> None:
    """`offset` меньше нуля отклоняется."""
    assert client.get("/v1/scenarios?offset=-1").status_code == 422


def test_delete_removes_scenario(client: TestClient) -> None:
    """Удаление отвечает 204, повторное — 404 (§5.8)."""
    created = client.post("/v1/scenarios", json=publish_body()).json()

    first = client.delete(f"/v1/scenarios/{created['id']}")
    second = client.delete(f"/v1/scenarios/{created['id']}")

    assert first.status_code == 204
    assert first.content == b""
    assert second.status_code == 404
    assert client.get(f"/v1/scenarios/{created['id']}").status_code == 404


def test_delete_invalid_uuid_is_422(client: TestClient) -> None:
    """Невалидный UUID при удалении — 422."""
    assert client.delete("/v1/scenarios/xyz").status_code == 422


def test_problem_json_contains_required_fields(client: TestClient) -> None:
    """Все поля RFC 7807 на месте, `Content-Type` — problem+json (§4)."""
    response = client.get("/v1/scenarios/00000000-0000-4000-8000-000000000000")

    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert set(body) == {"type", "title", "status", "detail", "instance", "request_id"}
    assert body["instance"] == "/v1/scenarios/00000000-0000-4000-8000-000000000000"


def test_empty_body_is_422(client: TestClient) -> None:
    """Пустое тело — 422, а не ошибка разбора."""
    response = client.post(
        "/v1/scenarios", content=b"", headers={"Content-Type": "application/json"}
    )

    assert response.status_code == 422
    assert response.json()["errors"][0]["path"] == "$"


def test_too_long_description_is_422(client: TestClient) -> None:
    """Описание длиннее 2000 символов отклоняется с путём `description`."""
    response = client.post("/v1/scenarios", json=publish_body(description="д" * 2001))

    assert response.status_code == 422
    assert response.json()["errors"][0]["path"] == "description"


def test_too_long_name_is_422(client: TestClient) -> None:
    """Имя длиннее 200 символов отклоняется с путём `name`."""
    response = client.post("/v1/scenarios", json=publish_body(name="a" * 201))

    assert response.status_code == 422
    assert response.json()["errors"][0]["path"] == "name"


def test_openapi_contains_scenario_endpoints(client: TestClient) -> None:
    """OpenAPI описывает пути сценариев контракта."""
    paths = client.get("/openapi.json").json()["paths"]

    assert {"/v1/scenarios", "/v1/scenarios/{scenario_id}"} <= set(paths)
    assert "post" in paths["/v1/scenarios"]
    assert "delete" in paths["/v1/scenarios/{scenario_id}"]


def test_database_unavailable_is_503(client: TestClient) -> None:
    """Запрос к сценариям без подключения к БД — 503, а не падение."""
    from service.app.config import Settings
    from service.app.main import create_app
    from tests.service.fakes import FakeDatabase

    app = create_app(
        Settings(api_key="test-key-0123456789", db_url="sqlite://"),
        database=FakeDatabase(),
    )
    with TestClient(app) as bare:
        response = bare.get("/v1/scenarios")

    assert response.status_code == 503
    assert response.json()["type"] == "urn:clikit:error:unavailable"


def test_list_after_delete_reports_new_total(client: TestClient) -> None:
    """`total` уменьшается после удаления."""
    created = client.post("/v1/scenarios", json=publish_body()).json()
    client.delete(f"/v1/scenarios/{created['id']}")

    assert client.get("/v1/scenarios").json()["total"] == 0


def test_body_limit_is_shared_across_routes(client: TestClient) -> None:
    """Лимит тела действует до маршрутизации — общий слой, а не логика сценариев."""
    huge = b'{"name":"' + b"x" * (1_048_576 + 10) + b'"}'

    response = client.post(
        "/healthz", content=huge, headers={"Content-Type": "application/json"}
    )

    assert response.status_code == 413
    assert response.json()["type"] == "urn:clikit:error:payload-too-large"


def test_body_limit_follows_settings(database) -> None:
    """Предел берётся из `CLICKIT_MAX_BODY_BYTES`, а не зашит в код (§9)."""
    from service.app.config import Settings
    from service.app.main import create_app

    app = create_app(
        Settings(api_key=API_KEY, db_url=database.url, max_body_bytes=2048),
        database=database,
    )
    body = json.dumps(publish_body(description="д" * 4096))

    with TestClient(app) as small:
        rejected = small.post(
            "/v1/scenarios", content=body, headers={"Content-Type": "application/json"}
        )
        accepted = small.post(
            "/v1/scenarios",
            content=json.dumps(publish_body()),
            headers={
                "Content-Type": "application/json",
                "X-API-Key": API_KEY,
            },
        )

    assert rejected.status_code == 413
    assert accepted.status_code == 201


def test_request_body_hash_is_stable(client: TestClient) -> None:
    """Хэш тела не зависит от порядка ключей и посторонних полей (§7)."""
    first = {"scenario": SAMPLE_SCENARIO, "name": "demo"}
    second = {"name": "demo", "scenario": SAMPLE_SCENARIO, "extra": 1}

    assert request_body_hash(first) == request_body_hash(second)


def test_expired_reservation_with_same_body_creates_new_row(
    client: TestClient, database
) -> None:
    """Ключ старше TTL снимается, и создаётся новая строка (§7, п. 5)."""
    first = client.post(
        "/v1/scenarios",
        json=publish_body(),
        headers={"Idempotency-Key": IDEMPOTENCY_KEY},
    ).json()
    stale = datetime.now(UTC) - timedelta(hours=48)
    with database.session_scope() as session:
        session.execute(
            update(Scenario)
            .where(Scenario.id == uuid.UUID(first["id"]))
            .values(created_at=stale)
        )

    second = client.post(
        "/v1/scenarios",
        json=publish_body(name="other"),
        headers={"Idempotency-Key": IDEMPOTENCY_KEY},
    )

    assert second.status_code == 201
    assert second.headers.get("Idempotent-Replay") != "true"
    assert second.json()["id"] != first["id"]
    assert client.get("/v1/scenarios").json()["total"] == 2
