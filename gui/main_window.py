"""Главное окно ClicKit: режимы, управление кликами, трей, закрытие окна."""

import logging

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core.executor import StopReason
from core.input.backend import InputBackend
from core.settings import Settings, SettingsStore
from gui.editor.editor_view import EditorView
from gui.executor_adapter import ExecutorAdapter
from gui.hotkey_bridge import HotkeyBridge
from gui.icons import app_icon
from gui.picker import CoordinatePicker
from gui.simple_mode.view import SimpleModeView
from gui.tray import TrayIcon

logger = logging.getLogger(__name__)

#: Постоянная подсказка в статус-баре.
HOTKEY_HINT = "F5 — старт · F6 — стоп · F8 — точка"

#: Действия при закрытии окна (значения совпадают с `core.settings`).
CLOSE_ASK = "ask"
CLOSE_TRAY = "tray"
CLOSE_QUIT = "quit"


class MainWindow(QMainWindow):
    """Главное окно: «Простой режим», заглушка редактора, трей и статус-бар."""

    def __init__(
        self,
        settings: Settings | None = None,
        store: SettingsStore | None = None,
        backend: InputBackend | None = None,
        enable_hotkeys: bool = True,
    ) -> None:
        """Создать окно.

        Args:
            settings: настройки, уже загруженные вызывающим кодом.
            store: хранилище настроек (по умолчанию — `%APPDATA%\\ClicKit`).
            backend: бэкенд ввода; `None` — pyautogui (в тестах — mock).
            enable_hotkeys: регистрировать ли глобальные хоткеи (в тестах — нет).
        """
        super().__init__()
        self._store = store if store is not None else SettingsStore()
        loaded = settings if settings is not None else self._store.load()
        self._settings = loaded.normalized()
        self._clicks = 0
        self._shutting_down = False
        self._tray_hint_shown = False
        self._tray_available = TrayIcon.is_available()

        self._adapter = ExecutorAdapter(backend, parent=self)
        self._picker = CoordinatePicker(self._adapter.backend, parent=self)
        self._hotkeys = HotkeyBridge(self._settings, parent=self)

        self._build_ui()
        self._connect()
        self._simple_view.apply_settings(self._settings)
        if enable_hotkeys:
            self._hotkeys.start()
        if self._tray_available:
            self._tray.show()
            self._tray.set_running(False)
        else:
            logger.warning("Системный трей недоступен — закрытие окна завершает работу")

    # --- построение интерфейса -------------------------------------------------

    def _build_ui(self) -> None:
        """Собрать заголовок, вкладки режимов и статус-бар."""
        self.setWindowTitle("ClicKit — автокликер")
        self.setWindowIcon(app_icon())
        self.resize(1024, 680)
        self.setMinimumSize(760, 520)

        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(16, 16, 16, 8)
        layout.setSpacing(12)

        title = QLabel("ClicKit")
        title.setObjectName("app-title")
        subtitle = QLabel("автокликер с визуальными сценариями")
        subtitle.setObjectName("muted")

        header = QHBoxLayout()
        header.addWidget(title)
        header.addWidget(subtitle)
        header.addStretch(1)
        layout.addLayout(header)

        self._simple_view = SimpleModeView()
        self._editor_view = EditorView()
        self._tabs = QTabWidget()
        self._tabs.addTab(self._simple_view, "Простой режим")
        self._tabs.addTab(self._editor_view, "Редактор сценариев")
        layout.addWidget(self._tabs, 1)
        self.setCentralWidget(central)

        hint = QLabel(HOTKEY_HINT)
        hint.setObjectName("muted")
        self.statusBar().addPermanentWidget(hint)
        self.statusBar().showMessage("Готов к работе")

        self._tray = TrayIcon(app_icon(), self)

    def _connect(self) -> None:
        """Связать форму, хоткеи, пикер, исполнитель и трей."""
        self._simple_view.start_requested.connect(self._start_clicks)
        self._simple_view.stop_requested.connect(self._stop_clicks)
        self._simple_view.pick_requested.connect(self._capture_point)
        self._simple_view.position_requested.connect(self._capture_point)

        self._hotkeys.start_requested.connect(self._start_clicks)
        self._hotkeys.stop_requested.connect(self._stop_clicks)
        self._hotkeys.pick_requested.connect(self._capture_point)

        self._picker.captured.connect(self._on_point_captured)
        self._picker.failed.connect(self._on_pick_failed)

        self._adapter.started.connect(self._on_started)
        self._adapter.step.connect(self._on_step)
        self._adapter.finished.connect(self._on_finished)

        self._tray.show_requested.connect(self._restore_window)
        self._tray.start_requested.connect(self._start_clicks)
        self._tray.stop_requested.connect(self._stop_clicks)
        self._tray.quit_requested.connect(self._quit)

    # --- запуск и остановка ----------------------------------------------------

    def _start_clicks(self) -> None:
        """Старт кликов: по кнопке, F5 или из меню трея."""
        if self._adapter.is_running:
            return
        try:
            config = self._simple_view.run_config()
        except ValueError as exc:
            self._simple_view.set_message(str(exc), error=True)
            return

        self._simple_view.apply_to(self._settings)
        self._store.save(self._settings)
        self._clicks = 0
        self._tabs.setCurrentWidget(self._simple_view)
        if not self._adapter.start(config):
            self.statusBar().showMessage(
                "Клики уже выполняются или предыдущий запуск ещё завершается"
            )

    def _stop_clicks(self) -> None:
        """Остановка кликов: по кнопке, F6 или из меню трея."""
        if not self._adapter.is_running:
            return
        self._adapter.stop()
        self._simple_view.set_message("Останавливаюсь…")
        self.statusBar().showMessage("Останавливаюсь…")

    def _on_started(self) -> None:
        """Исполнитель принял параметры и начал работу."""
        self._simple_view.set_running(True)
        self._simple_view.set_message("Кликаю…")
        self._simple_view.set_counter(0)
        self._tray.set_running(True)
        self.statusBar().showMessage("Клики выполняются — остановить: F6")
        if self.isHidden() and self._tray_available:
            self._tray.notify("Клики запущены", "Остановить: F6 или меню трея.")

    def _on_step(self, clicks: int) -> None:
        """Обновить счётчик выполненных кликов."""
        self._clicks = clicks
        self._simple_view.set_counter(clicks)
        self.statusBar().showMessage(f"Кликов: {clicks}")

    def _on_finished(self, reason_value: str, detail: str) -> None:
        """Вернуть интерфейс в состояние «готов» и показать причину остановки."""
        try:
            reason = StopReason(reason_value)
        except ValueError:  # pragma: no cover — неизвестная причина из ядра
            reason = StopReason.ERROR
            detail = detail or reason_value

        self._simple_view.set_running(False)
        self._tray.set_running(False)
        message = self._finish_message(reason, detail)
        self._simple_view.set_message(message, error=reason is StopReason.ERROR)
        self.statusBar().showMessage(message)

    def _finish_message(self, reason: StopReason, detail: str) -> str:
        """Текст статуса по причине завершения исполнения."""
        if reason is StopReason.COMPLETED:
            return f"Готово: выполнено кликов — {self._clicks}"
        if reason is StopReason.STOPPED:
            return f"Остановлено. Выполнено кликов: {self._clicks}"
        if reason is StopReason.FAILSAFE:
            return "Сработала защита: курсор в углу экрана — клики остановлены"
        return f"Ошибка: {detail}" if detail else "Ошибка выполнения"

    # --- пикер координат -------------------------------------------------------

    def _capture_point(self) -> None:
        """Снять позицию курсора (кнопка пикера или F8)."""
        if self._adapter.is_running:
            self.statusBar().showMessage("Сначала остановите клики (F6)")
            return
        self._picker.capture()

    def _on_point_captured(self, x: int, y: int) -> None:
        """Записать захваченные координаты в форму."""
        self._simple_view.set_point(x, y)
        message = f"Точка захвачена: ({x}, {y})"
        self._simple_view.set_message(message)
        self.statusBar().showMessage(message)

    def _on_pick_failed(self, detail: str) -> None:
        """Показать ошибку чтения позиции курсора."""
        message = f"Не удалось прочитать позицию курсора: {detail}"
        self._simple_view.set_message(message, error=True)
        self.statusBar().showMessage(message)

    # --- трей и закрытие -------------------------------------------------------

    def _restore_window(self) -> None:
        """Показать окно из трея и поднять его на передний план."""
        if self.isMinimized():
            self.showNormal()
        else:
            self.show()
        self.raise_()
        self.activateWindow()

    def _hide_to_tray(self, running: bool) -> None:
        """Спрятать окно в трей и один раз подсказать, как управлять кликами."""
        self.hide()
        if self._tray_hint_shown:
            return
        self._tray_hint_shown = True
        text = (
            "F6 — остановить клики."
            if running
            else "Клик по иконке в трее возвращает окно."
        )
        self._tray.notify("ClicKit свёрнут в трей", text)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 — имя из Qt
        """Спросить пользователя, свернуть окно в трей или выйти."""
        if self._shutting_down or not self._tray_available:
            self._quit()
            event.ignore()
            return

        running = self._adapter.is_running
        action = (
            self._settings.close_action_running
            if running
            else self._settings.close_action_idle
        )
        if action == CLOSE_ASK:
            action, remember = self._ask_close_action(running)
            if action == CLOSE_ASK:  # отмена
                event.ignore()
                return
            if remember:
                if running:
                    self._settings.close_action_running = action
                else:
                    self._settings.close_action_idle = action
                self._store.save(self._settings)

        event.ignore()
        if action == CLOSE_TRAY:
            self._hide_to_tray(running)
        else:
            self._quit()

    def _ask_close_action(self, running: bool) -> tuple[str, bool]:
        """Диалог закрытия. Возвращает (действие, запомнить ли выбор)."""
        box = QMessageBox(self)
        box.setWindowTitle("ClicKit")
        box.setIcon(QMessageBox.Icon.Question)
        if running:
            box.setText("Клики выполняются.")
            box.setInformativeText("Свернуть ClicKit в трей, чтобы не прерывать клики?")
        else:
            box.setText("Активных кликов нет.")
            box.setInformativeText("Свернуть ClicKit в трей?")

        tray_button = box.addButton(
            "Свернуть в трей",
            QMessageBox.ButtonRole.AcceptRole,
        )
        quit_button = box.addButton(
            "Остановить и выйти" if running else "Выйти",
            QMessageBox.ButtonRole.DestructiveRole,
        )
        box.addButton("Отмена", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(tray_button)

        remember = QCheckBox("Запомнить мой выбор")
        box.setCheckBox(remember)
        box.exec()

        clicked = box.clickedButton()
        if clicked is tray_button:
            return CLOSE_TRAY, remember.isChecked()
        if clicked is quit_button:
            return CLOSE_QUIT, remember.isChecked()
        return CLOSE_ASK, False

    def _quit(self) -> None:
        """Остановить клики, сохранить настройки и завершить приложение."""
        self._shutdown()
        QApplication.quit()

    def _shutdown(self) -> None:
        """Единая точка завершения: стоп, снятие хоткеев, сохранение настроек."""
        if self._shutting_down:
            return
        self._shutting_down = True
        self._adapter.stop(wait=True)
        self._hotkeys.stop()
        self._simple_view.apply_to(self._settings)
        self._store.save(self._settings)
        self._tray.hide()
        logger.info("Настройки сохранены: %s", self._store.path)
