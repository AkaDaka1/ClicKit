"""Пути к ресурсам проекта (устойчиво к запуску из любого каталога)."""

import sys
from pathlib import Path


def project_root() -> Path:
    """Корень проекта: папка с исходниками или распакованный бандл PyInstaller."""
    bundle = getattr(sys, "_MEIPASS", None)
    if isinstance(bundle, str):
        return Path(bundle)
    return Path(__file__).resolve().parents[1]


def resource_path(*parts: str) -> Path:
    """Путь к файлу внутри `resources/` (например, `styles/dark.qss`)."""
    return project_root().joinpath("resources", *parts)
