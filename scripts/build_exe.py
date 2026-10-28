"""Сборка ClicKit.exe через PyInstaller (onefile) с NOTICE рядом.

Запуск: `python scripts/build_exe.py`.
Требуется PyInstaller: `pip install -r requirements-build.txt`.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "packaging" / "ClicKit.spec"
NOTICE = ROOT / "packaging" / "NOTICE.txt"
DIST = ROOT / "dist"
EXE = DIST / "ClicKit.exe"


def main() -> int:
    """Собрать .exe, скопировать NOTICE и напечатать результат."""
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
    result = subprocess.run(command, cwd=ROOT, check=False)
    if result.returncode != 0:
        print("PyInstaller завершился с ошибкой — см. вывод выше.")
        return result.returncode

    if not EXE.exists():
        print(f"Не найден ожидаемый файл: {EXE}")
        return 1

    shutil.copy2(NOTICE, DIST / "NOTICE.txt")
    size_mb = EXE.stat().st_size / (1024 * 1024)
    print(f"Готово: {EXE} ({size_mb:.1f} МБ)")
    print(f"Лицензии рядом: {DIST / 'NOTICE.txt'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
