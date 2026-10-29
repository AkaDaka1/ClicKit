"""Проверка релиза: версия, артефакты, контрольные суммы и смоук-запуск.

Скрипт используется в CI/CD и локально после `scripts/build_exe.py`.

Запуск:
    python scripts/verify_release.py --tag v1.0.0 --no-artifacts  # только версия
    python scripts/verify_release.py                              # артефакты + суммы
    python scripts/verify_release.py --smoke                      # + запуск .exe
"""

from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
import tempfile
import time
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:  # запуск как `python scripts/verify_release.py`
    sys.path.insert(0, str(ROOT))

from app.version import APP_VERSION  # noqa: E402 — путь к корню нужен раньше

PYPROJECT = ROOT / "pyproject.toml"
DIST = ROOT / "dist"
CHECKSUMS_FILENAME = "SHA256SUMS.txt"
ZIP_FILENAME = "ClicKit-win64.zip"
NOTICE_FILENAME = "NOTICE.txt"
ONEDIR_EXE = Path("ClicKit") / "ClicKit.exe"
#: Нижняя граница размера архива: QtWebEngine весит сотни мегабайт,
#: поэтому мелкий архив означает неполную сборку.
MIN_ZIP_BYTES = 100 * 1024 * 1024
#: Сообщение, которое приложение пишет в журнал сразу после старта.
STARTUP_MARKER = "запускается"


def read_pyproject_version(path: Path = PYPROJECT) -> str:
    """Версия проекта из `pyproject.toml` (`[project].version`)."""
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return str(data["project"]["version"])


def check_version(tag: str | None = None) -> list[str]:
    """Сверить версии приложения, pyproject.toml и релизного тега."""
    problems: list[str] = []
    pyproject_version = read_pyproject_version()
    if pyproject_version != APP_VERSION:
        problems.append(
            f"pyproject.toml: version {pyproject_version} != APP_VERSION {APP_VERSION}"
        )
    if tag is not None:
        expected = tag[1:] if tag.startswith("v") else tag
        if expected != APP_VERSION:
            problems.append(f"тег {tag} != APP_VERSION {APP_VERSION}")
    return problems


def _display(path: Path) -> str:
    """Путь для сообщений: относительно корня проекта, если возможно."""
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def check_artifacts(dist: Path = DIST) -> list[str]:
    """Проверить наличие и содержимое релизных артефактов в `dist/`."""
    problems: list[str] = []

    archive = dist / ZIP_FILENAME
    notice = dist / NOTICE_FILENAME
    checksums = dist / CHECKSUMS_FILENAME

    for required in (archive, notice, checksums):
        if not required.is_file():
            problems.append(f"нет файла: {_display(required)}")

    if archive.is_file():
        if archive.stat().st_size < MIN_ZIP_BYTES:
            problems.append(
                f"{archive.name}: подозрительно мал "
                f"({archive.stat().st_size} байт, ожидается >= {MIN_ZIP_BYTES})"
            )
        try:
            with zipfile.ZipFile(archive) as bundle:
                names = set(bundle.namelist())
        except zipfile.BadZipFile:
            problems.append(f"{archive.name}: повреждённый zip-архив")
            names = set()
        for expected in (ONEDIR_EXE.as_posix(), f"ClicKit/{NOTICE_FILENAME}"):
            if names and expected not in names:
                problems.append(f"{archive.name}: нет записи {expected}")

    if checksums.is_file():
        problems.extend(check_checksums(dist))
    return problems


def check_checksums(dist: Path = DIST) -> list[str]:
    """Пересчитать SHA-256 и сравнить с `SHA256SUMS.txt`."""
    checksums = dist / CHECKSUMS_FILENAME
    if not checksums.is_file():
        return [f"нет файла: {_display(checksums)}"]

    problems: list[str] = []
    for line in checksums.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        digest, _, name = line.partition("  ")
        if len(digest) != 64 or not name:
            problems.append(f"{checksums.name}: некорректная строка: {line!r}")
            continue
        artifact = dist / name
        if not artifact.is_file():
            problems.append(f"{checksums.name}: нет артефакта {name}")
            continue
        actual = sha256(artifact)
        if actual != digest.lower():
            problems.append(f"{name}: SHA-256 не совпадает")
    return problems


def sha256(path: Path) -> str:
    """SHA-256 файла в hex."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def smoke_run(dist: Path = DIST, timeout: float = 120.0) -> list[str]:
    """Запустить onedir-сборку и убедиться, что приложение стартовало.

    Запуск идёт в offscreen-режиме с временным `%APPDATA%`, поэтому окно
    не открывается, а пользовательские настройки и журналы не затрагиваются.
    Признак успеха — строка о запуске в журнале приложения.
    """
    exe = dist / ONEDIR_EXE
    if not exe.is_file():
        return [f"нет файла для смоук-запуска: {_display(exe)}"]

    with tempfile.TemporaryDirectory(prefix="clickit-smoke-") as appdata:
        environment = dict(
            os.environ,
            APPDATA=appdata,
            QT_QPA_PLATFORM="offscreen",
            QTWEBENGINE_DISABLE_SANDBOX="1",
            QTWEBENGINE_CHROMIUM_FLAGS="--disable-gpu",
        )
        log_file = Path(appdata) / "ClicKit" / "logs" / "app.log"
        process = subprocess.Popen(
            [str(exe)],
            cwd=str(exe.parent),
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        started = False
        exit_code: int | None = None
        deadline = time.monotonic() + timeout
        try:
            while time.monotonic() < deadline:
                exit_code = process.poll()
                if exit_code is not None:
                    break
                if log_file.is_file() and STARTUP_MARKER in log_file.read_text(
                    encoding="utf-8", errors="replace"
                ):
                    started = True
                    break
                time.sleep(0.5)
        finally:
            _terminate(process)

    if started:
        return []
    if exit_code is not None:
        return [f"смоук-запуск: процесс завершился с кодом {exit_code} до старта"]
    return [f"смоук-запуск: за {timeout:g} с в журнале не появилось «{STARTUP_MARKER}»"]


def _terminate(process: subprocess.Popen[bytes]) -> None:
    """Завершить процесс сборки, не оставляя висящих окон."""
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=15)


def main(argv: list[str] | None = None) -> int:
    """Точка входа: напечатать найденные проблемы и вернуть код 0/1."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", help="релизный тег (например v1.0.0)")
    parser.add_argument("--dist", default=str(DIST), help="каталог артефактов")
    parser.add_argument(
        "--no-artifacts",
        action="store_true",
        help="проверять только версию (артефакты ещё не собраны)",
    )
    parser.add_argument("--smoke", action="store_true", help="запустить onedir-сборку")
    parser.add_argument(
        "--timeout", type=float, default=120.0, help="таймаут смоук-запуска, с"
    )
    args = parser.parse_args(argv)

    dist = Path(args.dist).resolve()
    problems = check_version(args.tag)
    if not args.no_artifacts:
        problems.extend(check_artifacts(dist))
    if args.smoke:
        problems.extend(smoke_run(dist, timeout=args.timeout))

    if problems:
        print("Проверка релиза не пройдена:")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    print(f"Проверка релиза пройдена (APP_VERSION {APP_VERSION}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
