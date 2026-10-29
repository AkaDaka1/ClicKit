"""Заметки релиза: раздел `CHANGELOG.md` для версии и признак pre-release.

Запуск:
    python scripts/release_notes.py --version 1.0.0 --output notes.md
    python scripts/release_notes.py --prerelease-flag prerelease.txt
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:  # запуск как `python scripts/release_notes.py`
    sys.path.insert(0, str(ROOT))

from app.version import APP_VERSION  # noqa: E402 — путь к корню нужен раньше

CHANGELOG = ROOT / "CHANGELOG.md"
HEADING = re.compile(r"^##\s+\[(?P<version>[^\]]+)\]")
LINK_DEFINITION = re.compile(r"^\[[^\]]+\]:\s*\S*\s*$")


def extract_notes(changelog: str, version: str) -> str:
    """Вернуть тело раздела `## [version]` без ссылок и пустых строк по краям."""
    lines = changelog.splitlines()
    start: int | None = None
    start_heading = None
    for index, line in enumerate(lines):
        match = HEADING.match(line)
        if match and match.group("version").strip() == version:
            start = index + 1
            start_heading = line.strip()
            break
    if start is None:
        raise LookupError(f"в CHANGELOG.md нет раздела для версии {version}")

    body: list[str] = []
    for line in lines[start:]:
        if HEADING.match(line) or line.startswith("## "):
            break
        if LINK_DEFINITION.match(line):
            continue
        body.append(line)

    text = "\n".join(body).strip()
    if not text:
        raise LookupError(f"раздел {start_heading!r} в CHANGELOG.md пуст")
    return f"{text}\n"


def is_prerelease(version: str) -> bool:
    """Версия считается предварительной, если содержит суффикс (`1.1.0-rc.1`)."""
    return "-" in version


def main(argv: list[str] | None = None) -> int:
    """Напечатать/сохранить заметки и, при необходимости, флаг pre-release."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", default=APP_VERSION, help="версия из CHANGELOG")
    parser.add_argument("--changelog", default=str(CHANGELOG))
    parser.add_argument("--output", help="файл для заметок (по умолчанию — stdout)")
    parser.add_argument(
        "--prerelease-flag",
        help="файл, куда записать true/false для GitHub Release",
    )
    args = parser.parse_args(argv)

    changelog = Path(args.changelog).read_text(encoding="utf-8")
    try:
        notes = extract_notes(changelog, args.version)
    except LookupError as error:
        print(error, file=sys.stderr)
        return 1

    if args.output:
        Path(args.output).write_text(notes, encoding="utf-8")
        print(f"Заметки релиза: {args.output}")
    else:
        print(notes, end="")

    if args.prerelease_flag:
        flag = "true" if is_prerelease(args.version) else "false"
        Path(args.prerelease_flag).write_text(flag, encoding="utf-8")
        print(f"Pre-release: {flag}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
