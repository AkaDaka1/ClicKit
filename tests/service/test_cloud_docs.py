"""Статические проверки документации ClicKit Cloud (M7 T6.1).

Документация — часть чекпоинта задачи, а не «файл рядом»: тест фиксирует
разделение ролей (`docs/api.md` — нормативный контракт, `docs/cloud.md` —
практическое руководство), ссылки из README и обязательные команды/лимиты,
чтобы инструкции не разъезжались с кодом и compose незаметно.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"

_LINK = re.compile(r"\]\(([^)#\s]+)(?:#[^)]*)?\)")
_EXTERNAL = ("http://", "https://", "mailto:")


def _text(name: str) -> str:
    """Прочитать документ из `docs/` в UTF-8."""
    return (DOCS / name).read_text(encoding="utf-8")


def _local_links(text: str) -> list[str]:
    """Выделить относительные ссылки Markdown, ведущие на файлы репозитория."""
    return [
        target for target in _LINK.findall(text) if not target.startswith(_EXTERNAL)
    ]


def test_cloud_guide_exists_and_links_contract() -> None:
    """Руководство описывает запуск/остановку и ссылается на контракт."""
    text = _text("cloud.md")
    assert "[`docs/api.md`](api.md)" in text
    assert "docker compose -f docker-compose.cloud.yml up -d" in text
    assert "docker compose -f docker-compose.cloud.yml down -v" in text


def test_contract_links_guide() -> None:
    """Контракт остаётся версионированным и ссылается на руководство."""
    text = _text("api.md")
    assert "[`docs/cloud.md`](cloud.md)" in text
    assert "Версия контракта: **1.0**" in text


def test_readme_links_both_cloud_documents() -> None:
    """README (EN и RU) — точка входа в обе части документации."""
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert text.count("[`docs/cloud.md`](docs/cloud.md)") >= 2
    assert text.count("[`docs/api.md`](docs/api.md)") >= 2


def test_relative_links_in_cloud_documents_exist() -> None:
    """Относительные ссылки в документации Cloud не битые."""
    for name in ("cloud.md", "api.md"):
        text = _text(name)
        for target in _local_links(text):
            assert (DOCS / target).resolve().exists(), f"{name}: нет {target}"


def test_quick_start_uses_required_env_names() -> None:
    """Руководство называет переменные, без которых сервис не стартует."""
    text = _text("cloud.md")
    for name in (
        "CLICKIT_API_KEY",
        "POSTGRES_PASSWORD",
        "CLICKIT_API_PORT",
        "CLICKIT_DB_URL",
        "CLICKIT_CLOUD_URL",
    ):
        assert name in text


def test_guide_documents_endpoints_errors_and_limits() -> None:
    """Эндпоинты, коды ошибок и лимит тела описаны в руководстве."""
    text = _text("cloud.md")
    for fragment in (
        "/healthz",
        "/readyz",
        "/version",
        "/v1/scenarios",
        "/v1/crash-reports",
        "401",
        "403",
        "404",
        "409",
        "413",
        "415",
        "422",
        "503",
        "1 МБ",
    ):
        assert fragment in text


def test_guide_documents_cli_exit_codes() -> None:
    """CLI и коды выхода контракта описаны в руководстве."""
    text = _text("cloud.md")
    for fragment in (
        "scripts/cloud_publish.py",
        "0` — успех",
        "2` — ошибка",
        "3` — авторизация",
        "4` — не найдено",
        "5` — невалидные",
        "6` —",
    ):
        assert fragment in text
