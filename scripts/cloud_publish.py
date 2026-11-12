"""Публикация и скачивание сценариев ClicKit Cloud из консоли (M7 T4.2).

Контракт CLI — `docs/api.md` §10. Скрипт — тонкая обёртка над `CloudClient`:
проверяет аргументы, читает/пишет `.acl.json` и печатает понятный итог.

Примеры:
    python scripts/cloud_publish.py publish resources/examples/click_pause_loop.acl.json
    python scripts/cloud_publish.py download <id> --output out.acl.json
    python scripts/cloud_publish.py list --limit 5
    python scripts/cloud_publish.py delete <id>
    python scripts/cloud_publish.py crash-report report.json

Параметры `--url`/`--api-key` заменяются переменными окружения
`CLICKIT_CLOUD_URL` и `CLICKIT_API_KEY`.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cloud.client import (  # noqa: E402
    CloudAuthError,
    CloudClient,
    CloudConflictError,
    CloudError,
    CloudNotFoundError,
    CloudServerError,
    CloudTooLargeError,
    CloudValidationError,
)
from core.ir.schema import ScenarioValidationError  # noqa: E402
from core.ir.storage import (  # noqa: E402
    ScenarioFileError,
    load_scenario,
    write_json,
)

#: Коды выхода скрипта (`docs/api.md` §10).
EXIT_OK = 0
EXIT_USAGE = 2
EXIT_AUTH = 3
EXIT_NOT_FOUND = 4
EXIT_INVALID = 5
EXIT_NETWORK = 6

#: URL сервиса по умолчанию (локальный compose, `docs/api.md` §9).
DEFAULT_URL = "http://localhost:8000"


def build_parser() -> argparse.ArgumentParser:
    """Собрать парсер аргументов CLI.

    Returns:
        Парсер с подкомандами `publish`, `download`, `list`, `delete`,
        `crash-report`.
    """
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--url",
        default=None,
        help=f"базовый URL сервиса (по умолчанию $CLICKIT_CLOUD_URL или {DEFAULT_URL})",
    )
    common.add_argument(
        "--api-key",
        default=None,
        help="ключ записи (по умолчанию $CLICKIT_API_KEY)",
    )
    common.add_argument(
        "--timeout",
        type=float,
        default=5.0,
        help="таймаут одной попытки в секундах (по умолчанию 5)",
    )
    common.add_argument(
        "--attempts",
        type=int,
        default=3,
        help="число попыток для 5xx/таймаутов (по умолчанию 3)",
    )

    parser = argparse.ArgumentParser(
        description="Клиент ClicKit Cloud: публикация, скачивание, список сценариев",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    publish = subparsers.add_parser(
        "publish",
        parents=[common],
        help="опубликовать файл .acl.json",
    )
    publish.add_argument("file", type=Path, help="путь к файлу .acl.json")
    publish.add_argument("--name", default=None, help="имя публикации")
    publish.add_argument("--description", default=None, help="описание сценария")
    publish.add_argument(
        "--idempotency-key",
        default=None,
        help="ключ идемпотентности (повтор безопасен в течение 24 ч)",
    )

    download = subparsers.add_parser(
        "download",
        parents=[common],
        help="скачать сценарий по id",
    )
    download.add_argument("scenario_id", help="UUIDv4 сценария")
    download.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="файл для сохранения (по умолчанию имя из Content-Disposition)",
    )

    list_cmd = subparsers.add_parser(
        "list",
        parents=[common],
        help="список сценариев",
    )
    list_cmd.add_argument("--limit", type=int, default=20, help="размер страницы")
    list_cmd.add_argument("--offset", type=int, default=0, help="смещение")

    delete = subparsers.add_parser(
        "delete",
        parents=[common],
        help="удалить сценарий по id",
    )
    delete.add_argument("scenario_id", help="UUIDv4 сценария")

    crash = subparsers.add_parser(
        "crash-report",
        parents=[common],
        help="отправить crash-отчёт из JSON-файла",
    )
    crash.add_argument("file", type=Path, help="путь к JSON с полями отчёта")

    return parser


def main(argv: list[str] | None = None) -> int:
    """Точка входа CLI.

    Args:
        argv: Аргументы командной строки (по умолчанию `sys.argv[1:]`).

    Returns:
        Код выхода (`docs/api.md` §10).
    """
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    try:
        base_url = resolve_url(args.url)
        api_key = resolve_api_key(args.api_key)
        client = CloudClient(
            base_url,
            api_key=api_key,
            timeout=args.timeout,
            attempts=args.attempts,
        )
    except ValueError as exc:
        print(f"Ошибка аргументов: {exc}", file=sys.stderr)
        return EXIT_USAGE

    with client:
        try:
            return run_command(client, args)
        except CloudValidationError as exc:
            print(f"Сервис отклонил данные: {exc}", file=sys.stderr)
            for issue in exc.issues:
                print(f"  {issue['path']}: {issue['message']}", file=sys.stderr)
            return EXIT_INVALID
        except ScenarioValidationError as exc:
            print("Сценарий не прошёл проверку:", file=sys.stderr)
            for issue in exc.issues:
                print(f"  {issue.path}: {issue.message}", file=sys.stderr)
            return EXIT_INVALID
        except CloudAuthError as exc:
            print(f"Авторизация: {exc}", file=sys.stderr)
            return EXIT_AUTH
        except CloudNotFoundError as exc:
            print(f"Не найдено: {exc}", file=sys.stderr)
            return EXIT_NOT_FOUND
        except CloudConflictError as exc:
            print(f"Конфликт: {exc}", file=sys.stderr)
            return EXIT_INVALID
        except CloudTooLargeError as exc:
            print(f"Файл слишком большой: {exc}", file=sys.stderr)
            return EXIT_INVALID
        except CloudServerError as exc:
            print(f"Сервис недоступен: {exc}", file=sys.stderr)
            return EXIT_NETWORK
        except CloudError as exc:
            print(f"Ошибка сервиса: {exc}", file=sys.stderr)
            return EXIT_NETWORK
        except (OSError, ScenarioFileError) as exc:
            print(f"Ошибка файла: {exc}", file=sys.stderr)
            return EXIT_USAGE
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            print(f"Ошибка файла: некорректный JSON ({exc})", file=sys.stderr)
            return EXIT_INVALID


def run_command(client: CloudClient, args: argparse.Namespace) -> int:
    """Выполнить выбранную подкоманду.

    Args:
        client: Настроенный клиент сервиса.
        args: Разобранные аргументы CLI.

    Returns:
        Код выхода подкоманды.
    """
    if args.command == "publish":
        return command_publish(client, args)
    if args.command == "download":
        return command_download(client, args)
    if args.command == "list":
        return command_list(client, args)
    if args.command == "delete":
        return command_delete(client, args)
    if args.command == "crash-report":
        return command_crash_report(client, args)
    raise AssertionError(f"Неизвестная команда: {args.command}")


def command_publish(client: CloudClient, args: argparse.Namespace) -> int:
    """Прочитать `.acl.json`, проверить локально и опубликовать."""
    scenario = load_scenario(args.file)
    published = client.publish(
        scenario.to_mapping(),
        name=args.name,
        description=args.description,
        idempotency_key=args.idempotency_key,
    )
    print(f"Опубликовано: {published.id}")
    print(f"  имя: {published.name}")
    print(f"  sha256: {published.sha256}")
    if published.url:
        print(f"  url: {published.url}")
    return EXIT_OK


def command_download(client: CloudClient, args: argparse.Namespace) -> int:
    """Скачать документ и сохранить его атомарно."""
    document = client.download(args.scenario_id)
    path = args.output or default_output_name(document, args.scenario_id)
    saved = write_json(path, document)
    print(f"Сохранено: {saved}")
    return EXIT_OK


def command_list(client: CloudClient, args: argparse.Namespace) -> int:
    """Напечатать страницу списка сценариев."""
    page = client.list(limit=args.limit, offset=args.offset)
    if not page.items:
        print("Сценариев нет.")
        return EXIT_OK
    print(
        f"Всего: {page.total} (страница {page.offset}–{page.offset + len(page.items)})"
    )
    for item in page.items:
        print(f"  {item.id}  {item.name}  {item.created_at}")
    return EXIT_OK


def command_delete(client: CloudClient, args: argparse.Namespace) -> int:
    """Удалить сценарий."""
    client.delete(args.scenario_id)
    print(f"Удалено: {args.scenario_id}")
    return EXIT_OK


def command_crash_report(client: CloudClient, args: argparse.Namespace) -> int:
    """Отправить crash-отчёт из JSON-файла."""
    payload = read_json_file(args.file)
    if not isinstance(payload, dict):
        print("Файл отчёта должен содержать JSON-объект", file=sys.stderr)
        return EXIT_USAGE
    missing = [
        field
        for field in ("app_version", "error_hash")
        if not isinstance(payload.get(field), str)
    ]
    if missing:
        print(
            "В отчёте нет обязательных строковых полей: " + ", ".join(missing),
            file=sys.stderr,
        )
        return EXIT_USAGE
    receipt = client.report_crash(
        app_version=payload["app_version"],
        os=str(payload.get("os") or ""),
        error_hash=payload["error_hash"],
        traceback=payload.get("traceback"),
    )
    print(f"Принято: {receipt.id} ({receipt.received_at})")
    return EXIT_OK


def resolve_url(raw: str | None) -> str:
    """Определить базовый URL: аргумент → env → значение по умолчанию."""
    value = (raw or os.environ.get("CLICKIT_CLOUD_URL") or DEFAULT_URL).strip()
    return value or DEFAULT_URL


def resolve_api_key(raw: str | None) -> str | None:
    """Определить ключ записи: аргумент → env → `None` (публичные методы)."""
    value = raw or os.environ.get("CLICKIT_API_KEY") or ""
    return value.strip() or None


def read_json_file(path: Path) -> Any:
    """Прочитать JSON-файл в UTF-8 (BOM от Windows-редакторов допускается).

    Raises:
        OSError: файл не читается.
        ValueError: содержимое не JSON.
    """
    return json.loads(path.read_text(encoding="utf-8-sig"))


def default_output_name(document: dict[str, Any], scenario_id: str) -> Path:
    """Имя файла для скачанного сценария.

    Опирается на `document["name"]`, повторяя правила `Content-Disposition`:
    небезопасные символы заменяются, ведущие точки убираются.
    """
    raw = document.get("name")
    name = raw.strip() if isinstance(raw, str) else ""
    cleaned = re.sub(r"[^0-9A-Za-z_.\- ]+", "_", name).strip()
    cleaned = re.sub(r"\.{2,}", ".", cleaned).lstrip(".").strip()
    base = cleaned or scenario_id
    if base.endswith(".acl.json"):
        return Path(base)
    return Path(f"{base}.acl.json")


if __name__ == "__main__":
    sys.exit(main())
