# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller: ClicKit одним .exe или папкой (onedir).

Режим выбирается переменной окружения `CLICKIT_ONEFILE=1`; по умолчанию
собирается onedir — он стартует за секунды, тогда как onefile распаковывает
~220 МБ QtWebEngine при каждом запуске.
"""

import os
from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent
ONEFILE = os.environ.get("CLICKIT_ONEFILE", "0") == "1"

a = Analysis(
    [str(ROOT / "app" / "__main__.py")],
    pathex=[str(ROOT)],
    binaries=[],
    # Весь resources/ внутрь сборки: Blockly (JS, msg/, media/), темы,
    # иконки и примеры сценариев. app/paths.py ищет их в sys._MEIPASS
    # (onefile) или рядом с .exe (onedir).
    datas=[(str(ROOT / "resources"), "resources")],
    hiddenimports=[
        "PySide6.QtWebChannel",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

COMMON = dict(
    name="ClicKit",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / "resources" / "icons" / "app.ico"),
    version=str(ROOT / "packaging" / "version_info.txt"),
)

if ONEFILE:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], **COMMON)
else:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, **COMMON)
    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=False,
        name="ClicKit",
    )
