"""Статические проверки упаковки: иконка, spec, версия, NOTICE."""

import struct
from pathlib import Path

from app.version import APP_VERSION

ROOT = Path(__file__).resolve().parents[1]
ICON = ROOT / "resources" / "icons" / "app.ico"
SPEC = ROOT / "packaging" / "ClicKit.spec"
VERSION_INFO = ROOT / "packaging" / "version_info.txt"
NOTICE = ROOT / "packaging" / "NOTICE.txt"
BUILD_SCRIPT = ROOT / "scripts" / "build_exe.py"
REQUIREMENTS_BUILD = ROOT / "requirements-build.txt"

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def ico_entries(data: bytes) -> list[tuple[int, int, int]]:
    """Разобрать ICO: список (ширина, высота, смещение PNG)."""
    reserved, kind, count = struct.unpack("<HHH", data[:6])
    assert reserved == 0
    assert kind == 1
    entries: list[tuple[int, int, int]] = []
    for index in range(count):
        offset = 6 + index * 16
        width, height, _colors, _reserved, _planes, _bits, size, start = struct.unpack(
            "<BBBBHHII", data[offset : offset + 16]
        )
        assert size > 0
        assert data[start : start + len(PNG_SIGNATURE)] == PNG_SIGNATURE
        entries.append((width or 256, height or 256, start))
    return entries


def test_icon_has_required_sizes() -> None:
    """ICO собран из PNG-кадров, включая 16 и 256 пикселей."""
    entries = ico_entries(ICON.read_bytes())
    sizes = {(width, height) for width, height, _start in entries}

    assert len(entries) == 7
    assert (16, 16) in sizes
    assert (256, 256) in sizes
    assert (32, 32) in sizes


def test_spec_includes_resources_and_metadata() -> None:
    """Spec кладёт resources/, иконку и версию; умеет onedir и onefile."""
    text = SPEC.read_text(encoding="utf-8")

    assert 'datas=[(str(ROOT / "resources"), "resources")]' in text
    assert "app.ico" in text
    assert "version_info.txt" in text
    assert "console=False" in text
    assert "PySide6.QtWebEngineCore" in text
    assert "CLICKIT_ONEFILE" in text
    assert "COLLECT(" in text
    compile(text, str(SPEC), "exec")


def test_version_info_matches_app_version() -> None:
    """Версия в свойствах .exe совпадает с APP_VERSION."""
    text = VERSION_INFO.read_text(encoding="utf-8")
    major, minor, patch = APP_VERSION.split(".")

    assert f"filevers=({major}, {minor}, {patch}, 0)" in text
    assert f"StringStruct('FileVersion', '{APP_VERSION}')" in text
    assert f"StringStruct('ProductVersion', '{APP_VERSION}')" in text


def test_notice_covers_third_party_licenses() -> None:
    """NOTICE упоминает LGPL (Qt, pynput), Apache (Blockly) и MIT."""
    text = NOTICE.read_text(encoding="utf-8")

    assert "LGPL v3" in text
    assert "Apache License 2.0" in text
    assert "MIT" in text
    assert "Blockly" in text
    assert "PySide6" in text


def test_build_script_and_requirements_exist() -> None:
    """Скрипт сборки умеет onedir/onefile/zip/both и копирует NOTICE."""
    script = BUILD_SCRIPT.read_text(encoding="utf-8")

    assert "PyInstaller" in script
    assert "NOTICE.txt" in script
    assert "ClicKit.spec" in script
    for mode in ("--onefile", "--zip", "--both"):
        assert mode in script
    assert "SHA256SUMS.txt" in script
    assert "pyinstaller" in REQUIREMENTS_BUILD.read_text(encoding="utf-8").lower()
