"""Сборка ClicKit через PyInstaller: папка (onedir) или один .exe (onefile).

Запуск:
    python scripts/build_exe.py          # onedir: dist/ClicKit/ClicKit.exe
    python scripts/build_exe.py --onefile
    python scripts/build_exe.py --zip    # onedir + zip-архив для релиза
    python scripts/build_exe.py --both   # zip + один .exe (релиз 1.0.0)

После сборки рядом появляются `NOTICE.txt` и `SHA256SUMS.txt`.
Требуется PyInstaller: `pip install -r requirements-build.txt`.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "packaging" / "ClicKit.spec"
NOTICE = ROOT / "packaging" / "NOTICE.txt"
DIST = ROOT / "dist"
CHECKSUMS_FILENAME = "SHA256SUMS.txt"


def main(argv: list[str] | None = None) -> int:
    """Собрать ClicKit, скопировать NOTICE и напечатать результат."""
    args = sys.argv[1:] if argv is None else argv
    if "--both" in args:
        # Релиз 1.0.0: быстрый onedir-архив и один .exe для тех, кому важен
        # единственный файл. Каждая сборка идёт отдельным запуском PyInstaller.
        rest = [arg for arg in args if arg != "--both"]
        for target in ("--zip", "--onefile"):
            code = main([*rest, target])
            if code != 0:
                return code
        return 0

    onefile = "--onefile" in args
    make_zip = "--zip" in args

    try:
        import PyInstaller  # noqa: F401 — проверка наличия сборщика
    except ImportError:
        print(
            "PyInstaller не установлен.\n"
            "Установите зависимости сборки: pip install -r requirements-build.txt"
        )
        return 1

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        str(SPEC),
    ]
    print("Сборка:", " ".join(str(part) for part in command))
    environment = dict(os.environ, CLICKIT_ONEFILE="1" if onefile else "0")
    result = subprocess.run(command, cwd=ROOT, check=False, env=environment)
    if result.returncode != 0:
        print("PyInstaller завершился с ошибкой — см. вывод выше.")
        return result.returncode

    exe = DIST / "ClicKit.exe" if onefile else DIST / "ClicKit" / "ClicKit.exe"
    if not exe.exists():
        print(f"Не найден ожидаемый файл: {exe}")
        return 1

    shutil.copy2(NOTICE, exe.parent / "NOTICE.txt")
    # Для GitHub Release нужен NOTICE.txt в корне dist/ (рядом с архивом).
    if (exe.parent / "NOTICE.txt") != DIST / "NOTICE.txt":
        shutil.copy2(NOTICE, DIST / "NOTICE.txt")
    target = exe if onefile else exe.parent
    size_mb = _directory_size(target) / (1024 * 1024)
    print(f"Готово: {exe} ({size_mb:.1f} МБ)")
    print(f"Лицензии рядом: {exe.parent / 'NOTICE.txt'}")

    if make_zip and not onefile:
        archive = shutil.make_archive(
            str(DIST / "ClicKit-win64"), "zip", DIST, "ClicKit"
        )
        print(f"Архив для релиза: {archive}")

    checksums = write_checksums()
    if checksums is not None:
        print(f"Контрольные суммы: {checksums}")
    return 0


def write_checksums() -> Path | None:
    """Записать SHA-256 готовых артефактов релиза в `dist/SHA256SUMS.txt`."""
    artifacts = [DIST / "ClicKit-win64.zip", DIST / "ClicKit.exe"]
    lines: list[str] = []
    for artifact in artifacts:
        if not artifact.is_file():
            continue
        digest = hashlib.sha256()
        with artifact.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        lines.append(f"{digest.hexdigest()}  {artifact.name}")

    if not lines:
        return None
    target = DIST / CHECKSUMS_FILENAME
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


def _directory_size(path: Path) -> int:
    """Суммарный размер файлов в каталоге (для onefile — самого файла)."""
    if path.is_file():
        return path.stat().st_size
    return sum(file.stat().st_size for file in path.rglob("*") if file.is_file())


if __name__ == "__main__":
    sys.exit(main())
