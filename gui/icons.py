"""Иконка приложения: SVG из `resources/icons` с программным запасным вариантом."""

from functools import lru_cache

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap, QPolygonF

from app.paths import resource_path

#: Файл иконки относительно `resources/icons`.
ICON_FILENAME = "app.svg"

#: Цвет акцента темы (совпадает с `resources/styles/dark.qss`).
ACCENT_COLOR = "#5865f2"


@lru_cache(maxsize=4)
def app_icon() -> QIcon:
    """Иконка ClicKit для окна и трея.

    Сначала пробуем SVG из ресурсов; если файла нет или SVG-плагин недоступен,
    рисуем простую иконку программно — приложение не должно падать из-за ресурса.
    """
    icon = QIcon(str(resource_path("icons", ICON_FILENAME)))
    if not icon.isNull():
        return icon
    return _fallback_icon()


def _fallback_icon(size: int = 64) -> QIcon:
    """Нарисовать запасную иконку: скруглённый квадрат + стрелка курсора."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(ACCENT_COLOR))
    radius = size * 0.22
    painter.drawRoundedRect(QRectF(1, 1, size - 2, size - 2), radius, radius)

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

    return QIcon(pixmap)
