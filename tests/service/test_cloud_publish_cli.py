"""Тесты CLI публикации сценариев (`scripts/cloud_publish.py`, M7 T4.2).

Сервис подменяется `httpx.MockTransport`, файлы читаются/пишутся в `tmp_path`;
проверяются коды выхода контракта `docs/api.md` §10 и выбор URL/ключа из env.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

import scripts.cloud_publish as cli
from cloud import client as cloud_client
from cloud.client import CloudClient
from core.ir.schema import scenario_from_mapping

#: Пример IR для файла сценария.
SAMPLE_IR: dict[str, Any] = {
    "version": 1,
    "name": "demo",
    "nodes": [{"type": "click", "x": 100, "y": 200}],
}

#: Ответ `POST /v1/scenarios`.
CREATED: dict[str, Any] = {
    "id": "11111111-1111-4111-8111-111111111111",
    "name": "demo",
    "sha256": "a" * 64,
    "created_at": "2026-11-02T10:00:00Z",
    "updated_at": "2026-11-02T10:00:00Z",
    "url": "/v1/scenarios/11111111-1111-4111-8111-111111111111",
}


@pytest.fixture()
def handler_slot() -> dict[str, Any]:
    """Слот, куда тест кладёт обработчик mock-транспорта."""
    return {}


@pytest.fixture()
def patched_client(
    monkeypatch: pytest.MonkeyPatch,
    handler_slot: dict[str, Any],
) -> dict[str, Any]:
    """Подменить `CloudClient` в CLI клиентом с mock-transport."""
    calls: dict[str, Any] = {}

    def factory(
        base_url: str,
        *,
        api_key: str | None = None,
        timeout: float = 5.0,
        attempts: int = 3,
    ) -> CloudClient:
        calls.update({"base_url": base_url, "api_key": api_key, "timeout": timeout})
        return CloudClient(
            base_url,
            api_key=api_key,
            timeout=timeout,
            attempts=attempts,
            transport=httpx.MockTransport(handler_slot["handler"]),
        )

    monkeypatch.setattr(cli, "CloudClient", factory)
    monkeypatch.setattr(cloud_client.time, "sleep", lambda _seconds: None)
    monkeypatch.delenv("CLICKIT_CLOUD_URL", raising=False)
    monkeypatch.delenv("CLICKIT_API_KEY", raising=False)
    return calls


def scenario_file(tmp_path: Path) -> Path:
    """Записать пример `.acl.json` и вернуть путь."""
    path = tmp_path / "demo.acl.json"
    path.write_text(json.dumps(SAMPLE_IR), encoding="utf-8")
    return path


def test_publish_reads_validates_and_prints(
    tmp_path: Path,
    patched_client: dict[str, Any],
    handler_slot: dict[str, Any],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`publish` читает файл, валидирует IR и печатает id/url."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(201, json=CREATED)

    handler_slot["handler"] = handler
    code = cli.main(
        [
            "publish",
            str(scenario_file(tmp_path)),
            "--name",
            "demo",
            "--api-key",
            "test-key-0123456789",
        ]
    )

    out = capsys.readouterr().out
    assert code == cli.EXIT_OK
    assert CREATED["id"] in out
    assert patched_client["base_url"] == cli.DEFAULT_URL
    assert patched_client["api_key"] == "test-key-0123456789"
    body = json.loads(seen[0].content)
    # CLI кладёт в тело нормализованный IR (как `core.ir.schema`).
    assert body["scenario"] == scenario_from_mapping(SAMPLE_IR).to_mapping()
    assert body["name"] == "demo"


def test_publish_invalid_scenario_fails_locally(
    tmp_path: Path,
    patched_client: dict[str, Any],
    handler_slot: dict[str, Any],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Невалидный IR отклоняется до сети с кодом 5."""
    path = tmp_path / "bad.acl.json"
    path.write_text(json.dumps({"version": 1, "nodes": [{"type": "click"}]}))

    def handler(_request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("невалидный сценарий не должен уходить на сервер")

    handler_slot["handler"] = handler
    code = cli.main(["publish", str(path), "--api-key", "test-key-0123456789"])

    assert code == cli.EXIT_INVALID
    assert "nodes[0]" in capsys.readouterr().err


def test_publish_server_validation_reports_issues(
    tmp_path: Path,
    patched_client: dict[str, Any],
    handler_slot: dict[str, Any],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """422 от сервиса печатает пути ошибок и код 5."""
    issues = [{"path": "name", "message": "должно быть от 1 до 200 символов"}]

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            422,
            json={
                "type": "urn:clikit:error:validation",
                "detail": "ошибки",
                "errors": issues,
            },
        )

    handler_slot["handler"] = handler
    code = cli.main(
        ["publish", str(scenario_file(tmp_path)), "--api-key", "test-key-0123456789"]
    )

    assert code == cli.EXIT_INVALID
    assert "name: должно быть от 1 до 200 символов" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("status", "code"),
    [(401, cli.EXIT_AUTH), (403, cli.EXIT_AUTH), (404, cli.EXIT_NOT_FOUND)],
)
def test_exit_codes_for_auth_and_not_found(
    status: int,
    code: int,
    patched_client: dict[str, Any],
    handler_slot: dict[str, Any],
) -> None:
    """401/403 → 3, 404 → 4."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"detail": "нет"})

    handler_slot["handler"] = handler
    assert cli.main(["download", CREATED["id"]]) == code


def test_download_saves_normalized_document(
    tmp_path: Path,
    patched_client: dict[str, Any],
    handler_slot: dict[str, Any],
) -> None:
    """`download` сохраняет документ в указанный файл."""
    output = tmp_path / "out" / "saved.acl.json"

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=SAMPLE_IR)

    handler_slot["handler"] = handler
    code = cli.main(["download", CREATED["id"], "--output", str(output)])

    assert code == cli.EXIT_OK
    assert json.loads(output.read_text(encoding="utf-8")) == SAMPLE_IR


def test_download_default_name_from_document(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    patched_client: dict[str, Any],
    handler_slot: dict[str, Any],
) -> None:
    """Без `--output` имя берётся из IR (`name` → `<name>.acl.json`)."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"version": 1, "name": "../Shooter 1"})

    handler_slot["handler"] = handler
    monkeypatch.chdir(tmp_path)
    assert cli.main(["download", CREATED["id"]]) == cli.EXIT_OK
    assert (tmp_path / "_Shooter 1.acl.json").exists()


def test_list_prints_items(
    patched_client: dict[str, Any],
    handler_slot: dict[str, Any],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`list` печатает счётчик и строки сценариев."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"items": [CREATED], "total": 1, "limit": 20, "offset": 0}
        )

    handler_slot["handler"] = handler
    code = cli.main(["list"])

    out = capsys.readouterr().out
    assert code == cli.EXIT_OK
    assert "Всего: 1" in out
    assert CREATED["id"] in out


def test_delete_reports_success(
    patched_client: dict[str, Any],
    handler_slot: dict[str, Any],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`delete` печатает подтверждение и возвращает 0."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(204)

    handler_slot["handler"] = handler
    assert cli.main(["delete", CREATED["id"], "--api-key", "test-key-0123456789"]) == (
        cli.EXIT_OK
    )
    assert "Удалено" in capsys.readouterr().out


def test_crash_report_sends_file(
    tmp_path: Path,
    patched_client: dict[str, Any],
    handler_slot: dict[str, Any],
) -> None:
    """`crash-report` отправляет поля из JSON-файла."""
    report = tmp_path / "report.json"
    report.write_text(
        json.dumps(
            {
                "app_version": "1.0.0",
                "os": "Windows 11",
                "error_hash": "c" * 64,
                "traceback": "Traceback",
            }
        ),
        encoding="utf-8",
    )
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            202, json={"id": "33333333-3333-4333-8333-333333333333", "received_at": "x"}
        )

    handler_slot["handler"] = handler
    assert cli.main(["crash-report", str(report)]) == cli.EXIT_OK
    assert json.loads(seen[0].content)["app_version"] == "1.0.0"


def test_crash_report_missing_fields_is_usage_error(
    tmp_path: Path,
    patched_client: dict[str, Any],
    handler_slot: dict[str, Any],
) -> None:
    """Отчёт без `error_hash` — ошибка использования (2)."""
    report = tmp_path / "report.json"
    report.write_text(json.dumps({"app_version": "1.0.0"}), encoding="utf-8")
    handler_slot["handler"] = lambda _request: httpx.Response(202, json={})

    assert cli.main(["crash-report", str(report)]) == cli.EXIT_USAGE


def test_server_error_exit_code(
    patched_client: dict[str, Any],
    handler_slot: dict[str, Any],
) -> None:
    """Недоступный сервис → код 6."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"detail": "БД недоступна"})

    handler_slot["handler"] = handler
    assert cli.main(["list"]) == cli.EXIT_NETWORK


def test_url_and_key_from_environment(
    monkeypatch: pytest.MonkeyPatch,
    patched_client: dict[str, Any],
    handler_slot: dict[str, Any],
) -> None:
    """URL и ключ берутся из env, если не переданы аргументами."""
    handler_slot["handler"] = lambda _request: httpx.Response(204)
    monkeypatch.setenv("CLICKIT_CLOUD_URL", "http://cloud.local:9000/")
    monkeypatch.setenv("CLICKIT_API_KEY", "env-key-0123456789")

    assert cli.main(["delete", CREATED["id"]]) == cli.EXIT_OK
    assert patched_client["base_url"] == "http://cloud.local:9000/"
    assert patched_client["api_key"] == "env-key-0123456789"


def test_invalid_url_is_usage_error(
    patched_client: dict[str, Any],
    handler_slot: dict[str, Any],
) -> None:
    """URL без схемы — ошибка использования (2)."""
    handler_slot["handler"] = lambda _request: httpx.Response(204)
    assert cli.main(["list", "--url", "cloud.local"]) == cli.EXIT_USAGE


def test_missing_scenario_file_is_usage_error(
    tmp_path: Path,
    patched_client: dict[str, Any],
    handler_slot: dict[str, Any],
) -> None:
    """Отсутствующий файл — ошибка использования (2)."""
    handler_slot["handler"] = lambda _request: httpx.Response(201, json=CREATED)
    assert cli.main(["publish", str(tmp_path / "none.acl.json")]) == cli.EXIT_USAGE


def test_broken_json_file_is_invalid(
    tmp_path: Path,
    patched_client: dict[str, Any],
    handler_slot: dict[str, Any],
) -> None:
    """Битый JSON отчёта — код 5, а не трассировка."""
    report = tmp_path / "report.json"
    report.write_text("{не json", encoding="utf-8")
    handler_slot["handler"] = lambda _request: httpx.Response(202, json={})

    assert cli.main(["crash-report", str(report)]) == cli.EXIT_INVALID


def test_resolve_helpers_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """Без env и аргументов URL — локальный адрес, ключа нет."""
    monkeypatch.delenv("CLICKIT_CLOUD_URL", raising=False)
    monkeypatch.delenv("CLICKIT_API_KEY", raising=False)
    assert cli.resolve_url(None) == cli.DEFAULT_URL
    assert cli.resolve_api_key(None) is None


def test_default_output_name_rules() -> None:
    """Имя файла очищается от небезопасных символов и получает суффикс."""
    assert cli.default_output_name({"name": "demo"}, "id-1") == Path("demo.acl.json")
    assert cli.default_output_name({"name": "demo.acl.json"}, "id-1") == Path(
        "demo.acl.json"
    )
    assert cli.default_output_name({"name": ""}, "id-1") == Path("id-1.acl.json")
    assert cli.default_output_name({"name": "..\\x/y"}, "id-1") == Path("_x_y.acl.json")
