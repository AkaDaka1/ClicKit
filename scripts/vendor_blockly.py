"""Вендоринг Blockly: скачать pinned-версию и разложить нужные файлы.

Скрипт нужен только разработчику при обновлении Blockly: приложение и тесты
работают офлайн. Вендоренные файлы не редактируются — обновление только через
этот скрипт (см. AI_CONTEXT.md §4).
"""

from __future__ import annotations

import argparse
import shutil
import tarfile
import tempfile
import urllib.request
from pathlib import Path

#: Версия Blockly, зафиксированная в проекте.
BLOCKLY_VERSION = "13.4.0"
#: Адрес пакета в npm-реестре.
REGISTRY_URL = "https://registry.npmjs.org/blockly/-/blockly-{version}.tgz"
#: Каталог вендоринга.
VENDOR_DIR = Path(__file__).resolve().parents[1] / "resources" / "blockly"
#: Файлы пакета, которые нужны рантайму (источник → назначение).
FILES: tuple[tuple[str, str], ...] = (
    ("blockly_compressed.js", "blockly_compressed.js"),
    ("blocks_compressed.js", "blocks_compressed.js"),
    ("msg/ru.js", "msg/ru.js"),
    ("LICENSE", "LICENSE"),
)
#: Каталог с картинками, звуками и курсорами Blockly.
MEDIA_DIR = "media"
#: Файл с версией и источником вендоринга.
VERSION_FILE = "VERSION.txt"


def version_text(version: str) -> str:
    """Текст файла `VERSION.txt`."""
    return (
        f"Blockly {version}\n"
        f"Источник: {REGISTRY_URL.format(version=version)}\n"
        "Вендорено скриптом scripts/vendor_blockly.py; файлы не редактировать.\n"
        "Лицензия: Apache-2.0 (см. LICENSE).\n"
    )


def required_paths() -> tuple[Path, ...]:
    """Пути, которые должны существовать после вендоринга."""
    files = tuple(VENDOR_DIR / dest for _, dest in FILES)
    return files + (VENDOR_DIR / MEDIA_DIR / "sprites.svg",)


def check(version: str = BLOCKLY_VERSION) -> list[str]:
    """Проверить вендоринг. Вернуть список проблем (пустой — всё на месте)."""
    problems: list[str] = []
    for path in required_paths():
        if not path.is_file():
            problems.append(f"нет файла: {path}")
    version_file = VENDOR_DIR / VERSION_FILE
    if not version_file.is_file():
        problems.append(f"нет файла: {version_file}")
    else:
        text = version_file.read_text(encoding="utf-8")
        if version not in text:
            problems.append(f"{version_file} не содержит версию {version}")
    return problems


def download(version: str, target: Path) -> None:
    """Скачать tarball Blockly из npm-реестра."""
    url = REGISTRY_URL.format(version=version)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "ClicKit-vendor/1.0"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        target.write_bytes(response.read())


def extract(archive: Path, destination: Path) -> None:
    """Безопасно распаковать tarball (только относительные пути)."""
    with tarfile.open(archive, "r:gz") as tar:
        for member in tar.getmembers():
            member_path = Path(member.name)
            if member_path.is_absolute() or ".." in member_path.parts:
                continue
            tar.extract(member, destination)


def vendor(version: str = BLOCKLY_VERSION) -> None:
    """Скачать и разложить файлы Blockly в `resources/blockly/`."""
    with tempfile.TemporaryDirectory(prefix="clickit-blockly-") as tmp:
        tmp_dir = Path(tmp)
        archive = tmp_dir / "blockly.tgz"
        print(f"Скачиваю Blockly {version}…")
        download(version, archive)
        extract(archive, tmp_dir)
        package = tmp_dir / "package"

        VENDOR_DIR.mkdir(parents=True, exist_ok=True)
        for source_name, dest_name in FILES:
            source = package / source_name
            destination = VENDOR_DIR / dest_name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            print(f"  + {destination.relative_to(VENDOR_DIR.parent.parent)}")

        media_destination = VENDOR_DIR / MEDIA_DIR
        if media_destination.exists():
            shutil.rmtree(media_destination)
        shutil.copytree(package / MEDIA_DIR, media_destination)
        print(f"  + {media_destination.relative_to(VENDOR_DIR.parent.parent)}/")

    version_file = VENDOR_DIR / VERSION_FILE
    version_file.write_text(version_text(version), encoding="utf-8")
    print(f"  + {version_file.relative_to(VENDOR_DIR.parent.parent)}")


def main() -> int:
    """Точка входа: `--check` или вендоринг."""
    parser = argparse.ArgumentParser(
        description="Вендоринг Blockly для ClicKit (нужен только разработчику)."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="только проверить наличие файлов, без скачивания",
    )
    parser.add_argument(
        "--version",
        default=BLOCKLY_VERSION,
        help=f"версия Blockly (по умолчанию {BLOCKLY_VERSION})",
    )
    args = parser.parse_args()

    if not args.check:
        try:
            vendor(args.version)
        except OSError as exc:
            print(f"Ошибка вендоринга: {exc}")
            return 1

    problems = check(args.version)
    if problems:
        for problem in problems:
            print(f"ОШИБКА: {problem}")
        return 1
    print(f"Blockly {args.version} на месте: {VENDOR_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
