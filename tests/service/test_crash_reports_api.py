"""Тесты эндпоинта `POST /v1/crash-reports` (`docs/api.md` §5.9).

Проверяется приём crash-отчётов: 202, валидация 422, санитизация PII
(домашние каталоги → `<пользователь>`), обрезка traceback до 16 КБ.
"""

from __future__ import annotations

import uuid

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("sqlalchemy")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from service.app.models import CrashReport  # noqa: E402

#: Минимальный валидный отчёт.
VALID_REPORT: dict[str, str] = {
    "app_version": "1.0.0",
    "os": "Windows 11 Pro 23H2",
    "error_hash": "a" * 64,
    "traceback": (
        'Traceback (most recent call last):\n  File "test.py", line 1\nValueError'
    ),
}


def test_crash_report_accepted(client: TestClient) -> None:
    """Валидный отчёт — 202 с `id` и `received_at`."""
    response = client.post("/v1/crash-reports", json=VALID_REPORT)

    assert response.status_code == 202
    body = response.json()
    assert "id" in body
    assert body["received_at"].endswith("Z")


def test_crash_report_no_auth_required(client: TestClient) -> None:
    """Crash-отчёты публичные — ключ не нужен (§5.9)."""
    response = client.post("/v1/crash-reports", json=VALID_REPORT)

    assert response.status_code == 202


def test_crash_report_stored_in_database(client: TestClient, database) -> None:
    """Отчёт сохраняется в БД с нормализованными полями."""
    response = client.post("/v1/crash-reports", json=VALID_REPORT)
    report_id = response.json()["id"]

    with database.session_scope() as session:
        record = session.execute(
            select(CrashReport).where(CrashReport.id == uuid.UUID(report_id))
        ).scalar_one()
        assert record.app_version == "1.0.0"
        assert record.os == "Windows 11 Pro 23H2"
        assert record.error_hash == "a" * 64
        assert record.traceback is not None
        assert "Traceback" in record.traceback


def test_crash_report_sanitize_windows_path(client: TestClient, database) -> None:
    """Windows-пути `C:\\Users\\<имя>\\` заменяются на `<пользователь>`."""
    report = {
        **VALID_REPORT,
        "traceback": '  File "C:\\Users\\John\\app.py", line 42\n    main()',
    }
    response = client.post("/v1/crash-reports", json=report)
    report_id = response.json()["id"]

    with database.session_scope() as session:
        record = session.execute(
            select(CrashReport).where(CrashReport.id == uuid.UUID(report_id))
        ).scalar_one()
        assert "John" not in (record.traceback or "")
        assert "<пользователь>" in (record.traceback or "")


def test_crash_report_sanitize_unix_path(client: TestClient, database) -> None:
    """Unix-пути `/home/<имя>/` заменяются на `<пользователь>`."""
    report = {
        **VALID_REPORT,
        "traceback": '  File "/home/jane/app.py", line 10\n    raise ValueError()',
    }
    response = client.post("/v1/crash-reports", json=report)
    report_id = response.json()["id"]

    with database.session_scope() as session:
        record = session.execute(
            select(CrashReport).where(CrashReport.id == uuid.UUID(report_id))
        ).scalar_one()
        assert "jane" not in (record.traceback or "")
        assert "<пользователь>" in (record.traceback or "")


def test_crash_report_sanitize_macos_path(client: TestClient, database) -> None:
    """macOS-пути `/Users/<имя>/` заменяются на `<пользователь>`."""
    report = {
        **VALID_REPORT,
        "traceback": '  File "/Users/bob/project/main.py", line 5',
    }
    response = client.post("/v1/crash-reports", json=report)
    report_id = response.json()["id"]

    with database.session_scope() as session:
        record = session.execute(
            select(CrashReport).where(CrashReport.id == uuid.UUID(report_id))
        ).scalar_one()
        assert "bob" not in (record.traceback or "")
        assert "<пользователь>" in (record.traceback or "")


def test_crash_report_traceback_truncated_to_16kb(client: TestClient, database) -> None:
    """Traceback длиннее 16 КБ обрезается."""
    huge_traceback = "x" * 20_000
    report = {**VALID_REPORT, "traceback": huge_traceback}
    response = client.post("/v1/crash-reports", json=report)
    report_id = response.json()["id"]

    with database.session_scope() as session:
        record = session.execute(
            select(CrashReport).where(CrashReport.id == uuid.UUID(report_id))
        ).scalar_one()
        assert len(record.traceback or "") == 16_384


def test_crash_report_traceback_optional(client: TestClient) -> None:
    """`traceback` необязательное поле."""
    report = {
        "app_version": "1.0.0",
        "os": "Linux",
        "error_hash": "b" * 64,
    }
    response = client.post("/v1/crash-reports", json=report)

    assert response.status_code == 202


def test_crash_report_os_optional(client: TestClient) -> None:
    """`os` необязательное поле."""
    report = {
        "app_version": "1.0.0",
        "error_hash": "c" * 64,
        "traceback": "test",
    }
    response = client.post("/v1/crash-reports", json=report)

    assert response.status_code == 202


def test_crash_report_missing_app_version_is_422(client: TestClient) -> None:
    """`app_version` обязательно — 422."""
    report = {"error_hash": "d" * 64, "traceback": "test"}
    response = client.post("/v1/crash-reports", json=report)

    assert response.status_code == 422
    errors = response.json()["errors"]
    assert any(e["path"] == "app_version" for e in errors)


def test_crash_report_missing_error_hash_is_422(client: TestClient) -> None:
    """`error_hash` обязательно — 422."""
    report = {"app_version": "1.0.0", "traceback": "test"}
    response = client.post("/v1/crash-reports", json=report)

    assert response.status_code == 422
    errors = response.json()["errors"]
    assert any(e["path"] == "error_hash" for e in errors)


def test_crash_report_invalid_error_hash_is_422(client: TestClient) -> None:
    """`error_hash` должен быть 64 hex-символа — 422."""
    report = {**VALID_REPORT, "error_hash": "not-a-hash"}
    response = client.post("/v1/crash-reports", json=report)

    assert response.status_code == 422
    errors = response.json()["errors"]
    assert any(e["path"] == "error_hash" for e in errors)


def test_crash_report_error_hash_uppercase_normalized(client: TestClient) -> None:
    """`error_hash` приводится к нижнему регистру."""
    report = {**VALID_REPORT, "error_hash": "A" * 64}
    response = client.post("/v1/crash-reports", json=report)

    assert response.status_code == 202


def test_crash_report_app_version_too_long_is_422(client: TestClient) -> None:
    """`app_version` длиннее 64 символов — 422."""
    report = {**VALID_REPORT, "app_version": "x" * 65}
    response = client.post("/v1/crash-reports", json=report)

    assert response.status_code == 422
    errors = response.json()["errors"]
    assert any(e["path"] == "app_version" for e in errors)


def test_crash_report_os_too_long_is_422(client: TestClient) -> None:
    """`os` длиннее 64 символов — 422."""
    report = {**VALID_REPORT, "os": "x" * 65}
    response = client.post("/v1/crash-reports", json=report)

    assert response.status_code == 422
    errors = response.json()["errors"]
    assert any(e["path"] == "os" for e in errors)


def test_crash_report_wrong_content_type_is_415(client: TestClient) -> None:
    """`Content-Type` не JSON — 415."""
    response = client.post(
        "/v1/crash-reports",
        content=b"{}",
        headers={"Content-Type": "text/plain"},
    )

    assert response.status_code == 415


def test_crash_report_payload_too_large_is_413(client: TestClient) -> None:
    """Тело больше 1 МБ — 413."""
    huge = "x" * (1_048_576 + 100)
    response = client.post(
        "/v1/crash-reports",
        content=f'{{"traceback": "{huge}"}}'.encode(),
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 413


def test_crash_report_empty_body_is_422(client: TestClient) -> None:
    """Пустое тело — 422."""
    response = client.post(
        "/v1/crash-reports",
        content=b"",
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 422


def test_crash_report_malformed_json_is_422(client: TestClient) -> None:
    """Битый JSON — 422."""
    response = client.post(
        "/v1/crash-reports",
        content=b'{"app_version": ',
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 422


def test_crash_report_non_object_body_is_422(client: TestClient) -> None:
    """Тело-массив вместо объекта — 422."""
    response = client.post("/v1/crash-reports", json=[1, 2, 3])

    assert response.status_code == 422


def test_crash_report_unknown_fields_ignored(client: TestClient) -> None:
    """Неизвестные поля тела игнорируются."""
    report = {**VALID_REPORT, "extra_field": "ignored"}
    response = client.post("/v1/crash-reports", json=report)

    assert response.status_code == 202


def test_crash_report_multiple_validation_errors_collected(
    client: TestClient,
) -> None:
    """Все ошибки валидации собираются в один ответ."""
    report = {"os": "x" * 100}  # нет app_version, нет error_hash, os слишком длинный
    response = client.post("/v1/crash-reports", json=report)

    assert response.status_code == 422
    errors = response.json()["errors"]
    paths = {e["path"] for e in errors}
    assert {"app_version", "error_hash", "os"} <= paths


def test_openapi_contains_crash_endpoint(client: TestClient) -> None:
    """OpenAPI описывает `/v1/crash-reports`."""
    paths = client.get("/openapi.json").json()["paths"]

    assert "/v1/crash-reports" in paths
    assert "post" in paths["/v1/crash-reports"]
