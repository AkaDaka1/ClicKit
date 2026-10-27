"""Вкладка визуального редактора сценариев: Blockly в `QWebEngineView`.

Javascript-логика живёт в `resources/blockly/` (index.html + editor.js);
обмен с Python — только через QWebChannel и мост `ScenarioBridge`.
"""

import json
import logging
from collections.abc import Callable

from PySide6.QtCore import QUrl, Signal
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QVBoxLayout, QWidget

from app.paths import resource_path
from bridge.web_channel import ScenarioBridge
from core.input.backend import InputBackend
from gui.editor.scenario_adapter import ScenarioAdapter

logger = logging.getLogger(__name__)


class _EditorPage(QWebEnginePage):
    """Страница редактора: консоль JS пишется в журналы Python."""

    def javaScriptConsoleMessage(
        self,
        level: QWebEnginePage.JavaScriptConsoleMessageLevel,
        message: str,
        line_number: int,
        source_id: str,
    ) -> None:  # noqa: N802 — имя метода задано Qt
        """Перенаправить сообщения JS-консоли в logging."""
        if level is QWebEnginePage.JavaScriptConsoleMessageLevel.WarningMessageLevel:
            logger.warning("JS %s:%s %s", source_id, line_number, message)
        elif level is QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel:
            logger.error("JS %s:%s %s", source_id, line_number, message)
        else:
            logger.debug("JS %s:%s %s", source_id, line_number, message)


class EditorView(QWidget):
    """Редактор сценариев: webview с Blockly, мост и адаптер.

    Внешние сигналы:
        status_message: текст и признак ошибки для статус-бара окна.
        running_changed: изменилось ли выполнение сценария (для трея и защиты).
    """

    status_message = Signal(str, bool)
    running_changed = Signal(bool)

    def __init__(
        self,
        backend: InputBackend,
        is_busy_checker: Callable[[], bool] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        """Создать редактор.

        Args:
            backend: общий бэкенд ввода (тот же, что у простого режима).
            is_busy_checker: выполняется ли другой режим (для взаимного
                исключения кликов и сценария).
        """
        super().__init__(parent)
        self._adapter = ScenarioAdapter(backend, parent=self)
        self._bridge = ScenarioBridge(
            self._adapter,
            dialog_parent=self,
            is_busy_checker=is_busy_checker,
            parent=self,
        )

        self._web = QWebEngineView(self)
        page = _EditorPage(self._web)
        self._web.setPage(page)

        channel = QWebChannel(self._web)
        channel.registerObject("bridge", self._bridge)
        page.setWebChannel(channel)

        settings = page.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True
        )
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._web)

        self._bridge.status_changed.connect(self.status_message)
        self._bridge.running_changed.connect(self.running_changed)

        self._web.load(QUrl.fromLocalFile(str(resource_path("blockly", "index.html"))))

    @property
    def web(self) -> QWebEngineView:
        """Встроенный виджет веб-страницы (нужен тестам)."""
        return self._web

    @property
    def is_running(self) -> bool:
        """Выполняется ли сценарий прямо сейчас."""
        return self._adapter.is_running

    def request_run(self) -> None:
        """Запустить сценарий по запросу (кнопка F5, мост).

        Workspace запрашивается у JS: перевод в IR и запуск выполняет мост.
        """
        if self._adapter.is_running:
            return
        self._web.page().runJavaScript(
            "window.__ckReady && editorApi.exportForRun ? "
            "editorApi.exportForRun() : null",
            self._on_export_for_run,
        )

    def request_stop(self) -> None:
        """Остановить сценарий (F6, кнопка «Стоп» в трее)."""
        self._bridge.stop()

    def shutdown(self) -> None:
        """Остановить сценарий и снять нагрузку страницы."""
        self._adapter.stop(wait=True)
        self._web.stop()

    def _on_export_for_run(self, payload: object) -> None:
        """Обработать JSON `{name, workspace}` из JS и передать в мост."""
        if not isinstance(payload, str):
            self.status_message.emit(
                "Редактор ещё загружается — попробуйте позже", True
            )
            return
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            self.status_message.emit("Редактор вернул повреждённые данные", True)
            return
        if not isinstance(data, dict):
            self.status_message.emit("Редактор вернул неверный формат", True)
            return
        name = data.get("name")
        workspace = data.get("workspace")
        if not isinstance(name, str) or not isinstance(workspace, dict):
            self.status_message.emit("Редактор вернул неверный формат", True)
            return
        self._bridge.run(name, json.dumps(workspace, ensure_ascii=False))
