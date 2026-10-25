"""Заглушка редактора сценариев (Blockly появится в вехе M4)."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class EditorView(QWidget):
    """Вкладка «Редактор сценариев»: описание будущих возможностей."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Создать заглушку редактора."""
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(12)
        layout.addStretch(1)

        title = QLabel("Визуальный редактор сценариев")
        title.setObjectName("title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        subtitle = QLabel(
            "Появится в вехе M4: последовательности кликов, движений и задержек\n"
            "будут собираться перетаскиванием блоков, как в конструкторе."
        )
        subtitle.setObjectName("muted")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setWordWrap(True)

        features = QLabel(
            "• клики, движения мыши и задержки\n"
            "• циклы и условия\n"
            "• сохранение и загрузка сценариев\n"
            "• подсветка блока, который выполняется сейчас"
        )
        features.setObjectName("muted")
        features.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(16)
        layout.addWidget(features)
        layout.addStretch(2)
