"""Форма «Простого режима»: точка, кнопка мыши, интервал, повторы, старт/стоп."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core.input.backend import Button
from core.settings import (
    MAX_COORDINATE,
    MAX_INTERVAL_MS,
    MAX_REPEATS,
    MIN_COORDINATE,
    MIN_INTERVAL_MS,
    MIN_REPEATS,
    Settings,
)
from gui.simple_mode.config import SimpleRunConfig

#: Подписи кнопок мыши: значение для `Button` → текст в интерфейсе.
BUTTON_LABELS: tuple[tuple[str, str], ...] = (
    (Button.LEFT.value, "Левая"),
    (Button.RIGHT.value, "Правая"),
    (Button.MIDDLE.value, "Средняя"),
)

#: Текст кнопки запуска в зависимости от состояния.
START_TEXT = "Старт (F5)"
STOP_TEXT = "Стоп (F6)"


class SimpleModeView(QWidget):
    """Форма настройки автоклика по одной точке.

    Сигналы:
        start_requested: нажата кнопка «Старт».
        stop_requested: нажата кнопка «Стоп».
        pick_requested: нажата кнопка «Захватить точку».
        position_requested: нажата кнопка «Текущая позиция».
    """

    start_requested = Signal()
    stop_requested = Signal()
    pick_requested = Signal()
    position_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        """Создать форму с настройками по умолчанию."""
        super().__init__(parent)
        self._running = False
        self._start_key = "F5"
        self._stop_key = "F6"
        self._pick_key = "F8"
        self._start_text = f"Старт ({self._start_key})"
        self._stop_text = f"Стоп ({self._stop_key})"
        self._pick_text = f"Захватить точку ({self._pick_key})"
        self._build_ui()
        self._connect()

    # --- построение интерфейса -------------------------------------------------

    def _build_ui(self) -> None:
        """Собрать виджеты формы и разместить их по группам."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Две группы в ряд: точка и параметры кликов.
        groups = QHBoxLayout()
        groups.setSpacing(16)
        groups.addWidget(self._build_point_group(), 1)
        groups.addWidget(self._build_clicks_group(), 1)
        layout.addLayout(groups)
        layout.addStretch(1)

        self._message_label = QLabel("Готов к работе")
        self._message_label.setObjectName("message")
        self._message_label.setWordWrap(True)

        self._counter_label = QLabel("Кликов: 0")
        self._counter_label.setObjectName("counter")

        footer = QHBoxLayout()
        footer.addWidget(self._message_label, 1)
        footer.addWidget(self._counter_label)
        layout.addLayout(footer)

        self._start_button = QPushButton(self._start_text)
        self._start_button.setObjectName("primary")
        self._start_button.setMinimumHeight(46)
        self._start_button.setDefault(True)
        layout.addWidget(self._start_button)

    def _build_point_group(self) -> QGroupBox:
        """Группа «Точка клика»: координаты и кнопки захвата."""
        group = QGroupBox("Точка клика")
        form = QFormLayout(group)
        form.setSpacing(10)

        self._x_spin = _make_coordinate_spin()
        self._y_spin = _make_coordinate_spin()
        form.addRow("X:", self._x_spin)
        form.addRow("Y:", self._y_spin)

        self._pick_button = QPushButton(self._pick_text)
        self._update_pick_tooltip()
        self._current_button = QPushButton("Текущая позиция")
        self._current_button.setToolTip("Взять позицию курсора прямо сейчас")

        buttons_row = QHBoxLayout()
        buttons_row.addWidget(self._pick_button)
        buttons_row.addWidget(self._current_button)
        buttons_row.addStretch(1)
        form.addRow(buttons_row)
        return group

    def _build_clicks_group(self) -> QGroupBox:
        """Группа «Клики»: кнопка мыши, интервал и число повторов."""
        group = QGroupBox("Клики")
        form = QFormLayout(group)
        form.setSpacing(10)

        self._button_combo = QComboBox()
        for value, label in BUTTON_LABELS:
            self._button_combo.addItem(label, value)

        self._interval_spin = QSpinBox()
        self._interval_spin.setRange(MIN_INTERVAL_MS, MAX_INTERVAL_MS)
        self._interval_spin.setValue(Settings.interval_ms)
        self._interval_spin.setSingleStep(10)
        self._interval_spin.setSuffix(" мс")

        self._repeats_spin = QSpinBox()
        self._repeats_spin.setRange(MIN_REPEATS, MAX_REPEATS)
        self._repeats_spin.setValue(Settings.repeats)

        self._infinite_check = QCheckBox("Бесконечно")
        self._infinite_check.setToolTip(
            f"Кликать до остановки кнопкой или {self._stop_key}"
        )

        repeats_row = QHBoxLayout()
        repeats_row.addWidget(self._repeats_spin, 1)
        repeats_row.addWidget(self._infinite_check)

        form.addRow("Кнопка мыши:", self._button_combo)
        form.addRow("Интервал:", self._interval_spin)
        form.addRow("Повторов:", repeats_row)
        return group

    def _connect(self) -> None:
        """Подключить обработчики элементов формы."""
        self._start_button.clicked.connect(self._on_start_clicked)
        self._infinite_check.toggled.connect(self._on_infinite_toggled)
        self._pick_button.clicked.connect(self.pick_requested.emit)
        self._current_button.clicked.connect(self.position_requested.emit)

    # --- состояние и данные ----------------------------------------------------

    @property
    def is_running(self) -> bool:
        """Показывает ли форма, что клики выполняются."""
        return self._running

    def run_config(self) -> SimpleRunConfig:
        """Собрать параметры запуска по текущим значениям формы.

        Raises:
            ValueError: если значения формы недопустимы.
        """
        x = self._x_spin.value()
        y = self._y_spin.value()
        if x == 0 and y == 0:
            raise ValueError(
                "Точка (0, 0) — аварийный угол pyautogui, клики там сразу "
                "остановятся. Выберите другую точку или захватите её "
                f"по {self._pick_key}."
            )
        return SimpleRunConfig(
            x=x,
            y=y,
            button=Button(str(self._button_combo.currentData())),
            interval_ms=self._interval_spin.value(),
            repeats=None
            if self._infinite_check.isChecked()
            else self._repeats_spin.value(),
        )

    def apply_settings(self, settings: Settings) -> None:
        """Показать в форме сохранённые настройки."""
        self._x_spin.setValue(settings.x)
        self._y_spin.setValue(settings.y)
        index = self._button_combo.findData(settings.button)
        self._button_combo.setCurrentIndex(index if index >= 0 else 0)
        self._interval_spin.setValue(settings.interval_ms)
        self._repeats_spin.setValue(settings.repeats)
        self._infinite_check.setChecked(settings.infinite)
        self._repeats_spin.setEnabled(not settings.infinite)

    def set_hotkeys(self, start: str, stop: str, pick: str) -> None:
        """Обновить подписи кнопок после смены хоткеев."""
        self._start_key = start
        self._stop_key = stop
        self._pick_key = pick
        self._start_text = f"Старт ({start})"
        self._stop_text = f"Стоп ({stop})"
        self._pick_text = f"Захватить точку ({pick})"
        self._pick_button.setText(self._pick_text)
        self._update_pick_tooltip()
        self._infinite_check.setToolTip(f"Кликать до остановки кнопкой или {stop}")
        self._start_button.setText(
            self._stop_text if self._running else self._start_text
        )

    def apply_to(self, settings: Settings) -> None:
        """Записать значения формы в объект настроек (для сохранения)."""
        settings.x = self._x_spin.value()
        settings.y = self._y_spin.value()
        settings.button = str(self._button_combo.currentData())
        settings.interval_ms = self._interval_spin.value()
        settings.repeats = self._repeats_spin.value()
        settings.infinite = self._infinite_check.isChecked()

    def set_point(self, x: int, y: int) -> None:
        """Показать координаты в полях формы."""
        self._x_spin.setValue(x)
        self._y_spin.setValue(y)

    def set_running(self, running: bool) -> None:
        """Переключить форму между состояниями «работает» и «готов»."""
        self._running = running
        self._start_button.setText(self._stop_text if running else self._start_text)
        self._set_button_role("danger" if running else "primary")

        for widget in (
            self._x_spin,
            self._y_spin,
            self._pick_button,
            self._current_button,
            self._button_combo,
            self._interval_spin,
            self._infinite_check,
        ):
            widget.setEnabled(not running)
        self._repeats_spin.setEnabled(
            not running and not self._infinite_check.isChecked()
        )

    def set_counter(self, clicks: int) -> None:
        """Обновить счётчик выполненных кликов."""
        self._counter_label.setText(f"Кликов: {clicks}")

    def set_message(self, text: str, error: bool = False) -> None:
        """Показать сообщение о состоянии (обычное или ошибку)."""
        self._message_label.setText(text)
        self._message_label.setProperty("error", error)
        style = self._message_label.style()
        style.unpolish(self._message_label)
        style.polish(self._message_label)

    # --- обработчики -----------------------------------------------------------

    def _on_start_clicked(self) -> None:
        """Кнопка работает как переключатель: старт или стоп."""
        if self._running:
            self.stop_requested.emit()
        else:
            self.start_requested.emit()

    def _on_infinite_toggled(self, checked: bool) -> None:
        """При «Бесконечно» поле числа повторов недоступно."""
        self._repeats_spin.setEnabled(not checked and not self._running)

    def _set_button_role(self, role: str) -> None:
        """Сменить роль кнопки старта (`primary`/`danger`) и перекрасить её."""
        self._start_button.setObjectName(role)
        style = self._start_button.style()
        style.unpolish(self._start_button)
        style.polish(self._start_button)

    def _update_pick_tooltip(self) -> None:
        """Подсказка кнопки захвата с актуальным хоткеем."""
        self._pick_button.setToolTip(
            f"Наведите мышь на нужную точку экрана и нажмите {self._pick_key} — "
            "координаты попадут в поля"
        )


def _make_coordinate_spin() -> QSpinBox:
    """Создать спинбокс координаты с запасом под несколько мониторов."""
    spin = QSpinBox()
    spin.setRange(MIN_COORDINATE, MAX_COORDINATE)
    spin.setSuffix(" px")
    return spin
