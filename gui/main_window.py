"""Главное окно ClicKit: режимы, управление кликами, трей, закрытие окна."""

import logging
from html import escape

from PySide6.QtCore import QUrl
from PySide6.QtGui import QAction, QCloseEvent, QDesktopServices, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.logging_setup import log_dir, log_path
from app.version import APP_NAME, APP_VERSION
from core.executor import StopReason
from core.input.backend import InputBackend
from core.settings import Settings, SettingsStore
from gui.editor.editor_view import EditorView
from gui.executor_adapter import ExecutorAdapter
from gui.hotkey_bridge import HotkeyBridge
from gui.hotkey_spec import spec_to_text
from gui.icons import app_icon
from gui.picker import CoordinatePicker
from gui.settings_dialog import SettingsDialog
from gui.simple_mode.view import SimpleModeView
from gui.theme import ThemeManager
from gui.tray import TrayIcon

logger = logging.getLogger(__name__)


def hotkey_hint(settings: Settings) -> str:
    """Постоянная подсказка в статус-баре с текущими хоткеями."""
    start = spec_to_text(settings.hotkey_start)
    stop = spec_to_text(settings.hotkey_stop)
    pick = spec_to_text(settings.hotkey_pick)
    return f"{start} — старт активного режима · {stop} — стоп · {pick} — точка"


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
        theme: ThemeManager | None = None,
    ) -> None:
        """Создать окно.

        Args:
            settings: настройки, уже загруженные вызывающим кодом.
            store: хранилище настроек (по умолчанию — `%APPDATA%\\ClicKit`).
            backend: бэкенд ввода; `None` — pyautogui (в тестах — mock).
            enable_hotkeys: регистрировать ли глобальные хоткеи (в тестах — нет).
            theme: менеджер темы приложения; `None` — создать свой (без QSS).
        """
        super().__init__()
        self._store = store if store is not None else SettingsStore()
        loaded = settings if settings is not None else self._store.load()
        self._settings = loaded.normalized()
        self._theme = (
            theme
            if theme is not None
            else ThemeManager(self._settings.theme, parent=self)
        )
        self._clicks = 0
        self._shutting_down = False
        self._tray_hint_shown = False
        self._tray_available = TrayIcon.is_available()
        self._clicks_running = False
        self._scenario_running = False

        self._adapter = ExecutorAdapter(backend, parent=self)
        self._picker = CoordinatePicker(self._adapter.backend, parent=self)
        self._hotkeys = HotkeyBridge(self._settings, parent=self)

        self._build_ui()
        self._connect()
        self._simple_view.apply_settings(self._settings)
        self._sync_hotkey_labels()
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
        self._editor_view = EditorView(
            self._adapter.backend,
            is_busy_checker=lambda: self._adapter.is_running,
            theme=self._theme.effective,
        )
        self._tabs = QTabWidget()
        self._tabs.addTab(self._simple_view, "Простой режим")
        self._tabs.addTab(self._editor_view, "Редактор сценариев")
        layout.addWidget(self._tabs, 1)
        self.setCentralWidget(central)

        hint = QLabel(hotkey_hint(self._settings))
        hint.setObjectName("muted")
        self._hint_label = hint
        self.statusBar().addPermanentWidget(hint)
        self.statusBar().showMessage("Готов к работе")

        self._build_menu()

        self._tray = TrayIcon(app_icon(), self)

    def _build_menu(self) -> None:
        """Меню приложения: настройки, журналы и сведения о программе."""
        settings_menu = self.menuBar().addMenu("Настройки")
        params = QAction("Параметры…", self)
        params.setShortcut(QKeySequence("Ctrl+,"))
        params.setStatusTip("Тема оформления и глобальные хоткеи")
        params.triggered.connect(self._open_settings)
        settings_menu.addAction(params)

        help_menu = self.menuBar().addMenu("Помощь")
        logs = QAction("Открыть папку журналов", self)
        logs.setStatusTip(f"Журналы ClicKit: {log_dir()}")
        logs.triggered.connect(self._open_logs)
        help_menu.addAction(logs)

        about = QAction("О программе", self)
        about.triggered.connect(self._show_about)
        help_menu.addAction(about)

    def _open_logs(self) -> None:
        """Открыть папку журналов в проводнике."""
        directory = log_dir()
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self.statusBar().showMessage(f"Не удалось открыть журналы: {exc}")
            return
        if QDesktopServices.openUrl(QUrl.fromLocalFile(str(directory))):
            self.statusBar().showMessage(f"Открыта папка журналов: {directory}")
        else:
            self.statusBar().showMessage(f"Журналы: {directory}")

    def _show_about(self) -> None:
        """Показать версию и путь к журналу."""
        QMessageBox.about(
            self,
            f"О программе {APP_NAME}",
            f"<b>{APP_NAME}</b> {APP_VERSION}<br><br>"
            "Автокликер с визуальными сценариями.<br>"
            "Python + PySide6 + Blockly.<br><br>"
            f"Журнал: {escape(str(log_path()))}",
        )

    def _connect(self) -> None:
        """Связать форму, хоткеи, пикер, исполнитель и трей."""
        self._simple_view.start_requested.connect(self._start_clicks)
        self._simple_view.stop_requested.connect(self._stop_clicks)
        self._simple_view.pick_requested.connect(self._capture_point)
        self._simple_view.position_requested.connect(self._capture_point)

        self._hotkeys.start_requested.connect(self._start_active_mode)
        self._hotkeys.stop_requested.connect(self._stop_all)
        self._hotkeys.pick_requested.connect(self._capture_point)

        self._picker.captured.connect(self._on_point_captured)
        self._picker.failed.connect(self._on_pick_failed)

        self._adapter.started.connect(self._on_started)
        self._adapter.step.connect(self._on_step)
        self._adapter.finished.connect(self._on_finished)

        self._editor_view.status_message.connect(self._on_editor_status)
        self._editor_view.running_changed.connect(self._on_scenario_running)
        self._theme.changed.connect(self._editor_view.set_theme)

        self._tray.show_requested.connect(self._restore_window)
        self._tray.start_requested.connect(self._start_active_mode)
        self._tray.stop_requested.connect(self._stop_all)
        self._tray.quit_requested.connect(self._quit)

    # --- настройки -------------------------------------------------------------

    def _open_settings(self) -> None:
        """Открыть диалог настроек и применить изменения сразу."""
        dialog = SettingsDialog(self._settings, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._apply_settings(dialog)

    def _apply_settings(self, dialog: SettingsDialog) -> None:
        """Применить тему и хоткеи из диалога без перезапуска приложения."""
        hotkeys = dialog.hotkeys()
        self._settings.theme = dialog.theme_mode()
        self._settings.hotkey_start = hotkeys["start"]
        self._settings.hotkey_stop = hotkeys["stop"]
        self._settings.hotkey_pick = hotkeys["pick"]
        self._settings = self._settings.normalized()

        self._simple_view.apply_to(self._settings)
        self._theme.set_mode(self._settings.theme)
        self._hotkeys.reload(self._settings)
        self._sync_hotkey_labels()
        self._store.save(self._settings)
        self.statusBar().showMessage("Настройки сохранены")

    def _sync_hotkey_labels(self) -> None:
        """Показать актуальные хоткеи в подсказке, на кнопках и в редакторе."""
        start = spec_to_text(self._settings.hotkey_start)
        stop = spec_to_text(self._settings.hotkey_stop)
        pick = spec_to_text(self._settings.hotkey_pick)
        self._simple_view.set_hotkeys(start, stop, pick)
        self._editor_view.set_hotkeys(start, stop)
        self._hint_label.setText(hotkey_hint(self._settings))

    # --- запуск и остановка ----------------------------------------------------

    def _start_clicks(self) -> None:
        """Старт кликов: по кнопке, F5 или из меню трея."""
        if self._adapter.is_running:
            return
        if self._editor_view.is_running:
            message = "Сначала остановите сценарий (F6)"
            self._simple_view.set_message(message)
            self.statusBar().showMessage(message)
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

    def _start_active_mode(self) -> None:
        """Старт активного режима: на вкладке редактора — сценарий, иначе клики."""
        if self._tabs.currentWidget() is self._editor_view:
            self._start_scenario()
        else:
            self._start_clicks()

    def _start_scenario(self) -> None:
        """Старт сценария из редактора (F5 на вкладке редактора)."""
        if self._editor_view.is_running:
            return
        if self._adapter.is_running:
            message = "Сначала остановите клики (F6)"
            self._simple_view.set_message(message)
            self.statusBar().showMessage(message)
            return
        self._editor_view.request_run()

    def _stop_all(self) -> None:
        """Остановить и клики, и сценарий (F6 или меню трея)."""
        stopped = False
        if self._adapter.is_running:
            self._adapter.stop()
            self._simple_view.set_message("Останавливаюсь…")
            stopped = True
        if self._editor_view.is_running:
            self._editor_view.request_stop()
            stopped = True
        if stopped:
            self.statusBar().showMessage("Останавливаюсь…")

    def _on_editor_status(self, text: str, is_error: bool) -> None:
        """Статус редактора в статус-бар главного окна."""
        self.statusBar().showMessage(text)

    def _on_scenario_running(self, running: bool) -> None:
        """Сценарий начал/завершил работу: трей и защита от двойного запуска."""
        self._scenario_running = running
        self._sync_tray()
        if running and self.isHidden() and self._tray_available:
            self._tray.notify("Сценарий запущен", "Остановить: F6 или меню трея.")

    def _sync_tray(self) -> None:
        """Трей отражает, выполняется ли хоть какой-то режим."""
        if self._tray_available:
            self._tray.set_running(self._clicks_running or self._scenario_running)

    def _on_started(self) -> None:
        """Исполнитель принял параметры и начал работу."""
        self._simple_view.set_running(True)
        self._simple_view.set_message("Кликаю…")
        self._simple_view.set_counter(0)
        self._clicks_running = True
        self._sync_tray()
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
        self._clicks_running = False
        self._sync_tray()
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
            "F6 — остановить выполнение."
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

        running = self._adapter.is_running or self._editor_view.is_running
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
            box.setText("Выполняется сценарий или клики.")
            box.setInformativeText(
                "Свернуть ClicKit в трей, чтобы не прерывать выполнение?"
            )
        else:
            box.setText("Активных задач нет.")
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
        self._editor_view.shutdown()
        self._hotkeys.stop()
        self._simple_view.apply_to(self._settings)
        self._store.save(self._settings)
        self._tray.hide()
        logger.info("Настройки сохранены: %s", self._store.path)
