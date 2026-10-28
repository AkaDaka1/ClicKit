"""Сборка `resources/icons/app.ico` из векторной отрисовки иконки.

Скрипт детерминированный и не требует сторонних библиотек: рисует иконку
через QPainter в нескольких размерах и упаковывает PNG-кадры в ICO.
Запуск: `python scripts/make_icon.py`.
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path
from typing import Final

from PySide6.QtCore import QBuffer, QIODevice, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPolygonF

#: Размеры кадров: от панели задач до крупного значка в проводнике.
SIZES: Final[tuple[int, ...]] = (16, 24, 32, 48, 64, 128, 256)

#: Акцентный цвет бренда (совпадает с темами GUI и Blockly).
ACCENT_COLOR: Final[str] = "#5865f2"

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "resources" / "icons" / "app.ico"


def draw_icon(size: int) -> QImage:
    """Нарисовать иконку ClicKit заданного размера (прозрачный фон)."""
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)

    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(ACCENT_COLOR))
    radius = size * 0.22
    inset = max(1.0, size * 0.03)
    painter.drawRoundedRect(
        QRectF(inset, inset, size - 2 * inset, size - 2 * inset),
        radius,
        radius,
    )

    painter.setBrush(QColor("#ffffff"))
    cursor = QPolygonF(
        [
            QPointF(size * 0.30, size * 0.18),
            QPointF(size * 0.30, size * 0.74),
            QPointF(size * 0.44, size * 0.60),
            QPointF(size * 0.53, size * 0.83),
            QPointF(size * 0.64, size * 0.78),
            QPointF(size * 0.55, size * 0.56),
            QPointF(size * 0.74, size * 0.54),
        ]
    )
    painter.drawPolygon(cursor)
    painter.end()
    return image


def png_bytes(image: QImage) -> bytes:
    """Закодировать изображение в PNG (в памяти, без временных файлов)."""
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not image.save(buffer, "PNG"):
        raise RuntimeError("Не удалось закодировать PNG для иконки")
    data = bytes(buffer.data())
    buffer.close()
    return data


def build_ico(frames: dict[int, bytes]) -> bytes:
    """Собрать ICO-контейнер с PNG-записями (формат Vista+)."""
    count = len(frames)
    header = struct.pack("<HHH", 0, 1, count)
    entries = bytearray()
    offset = len(header) + 16 * count
    payload = bytearray()

    for size, data in sorted(frames.items()):
        if not 0 < size <= 256:
            raise ValueError(f"Недопустимый размер иконки: {size}")
        dimension = 0 if size == 256 else size
        entries += struct.pack(
            "<BBBBHHII",
            dimension,
            dimension,
            0,
            0,
            1,
            32,
            len(data),
            offset,
        )
        payload += data
        offset += len(data)

    return bytes(header + entries + payload)


def main() -> int:
    """Сгенерировать ICO и напечатать путь."""
    frames = {size: png_bytes(draw_icon(size)) for size in SIZES}
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_bytes(build_ico(frames))
    print(f"Иконка собрана: {OUTPUT} ({len(SIZES)} размеров)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
