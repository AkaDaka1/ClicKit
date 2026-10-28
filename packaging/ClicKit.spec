# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller: ClicKit одним .exe (windowed, ресурсы внутри)."""

from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent

a = Analysis(
    [str(ROOT / "app" / "__main__.py")],
    pathex=[str(ROOT)],
    binaries=[],
    # Весь resources/ внутрь сборки: Blockly (JS, msg/, media/), темы,
    # иконки и примеры сценариев. app/paths.py ищет их в sys._MEIPASS.
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

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
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
