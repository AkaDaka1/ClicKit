"""Вкладка визуального редактора сценариев: Blockly в `QWebEngineView`.

Javascript-логика живёт в `resources/blockly/` (index.html + editor.js);
обмен с Python — только через QWebChannel и мост `ScenarioBridge`.
Страница создаётся при первом показе вкладки: приложение стартует быстрее
и не держит Chromium в памяти, пока редактор не нужен.
"""

import json
import logging
from collections.abc import Callable
from urllib.parse import urlencode

from PySide6.QtCore import QTimer, QUrl, Signal
from PySide6.QtGui import QShowEvent
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
        theme: str = "dark",
        parent: QWidget | None = None,
    ) -> None:
        """Создать редактор.

        Args:
            backend: общий бэкенд ввода (тот же, что у простого режима).
            is_busy_checker: выполняется ли другой режим (для взаимного
                исключения кликов и сценария).
            theme: действующая тема (`dark`/`light`); применяется к Blockly.
        """
        super().__init__(parent)
        self._web: QWebEngineView | None = None
        self._theme = theme if theme in ("dark", "light") else "dark"
        self._hotkey_start = "F5"
        self._hotkey_stop = "F6"
        self._adapter = ScenarioAdapter(backend, parent=self)
        self._bridge = ScenarioBridge(
            self._adapter,
            dialog_parent=self,
            is_busy_checker=is_busy_checker,
            parent=self,
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._bridge.status_changed.connect(self.status_message)
        self._bridge.running_changed.connect(self.running_changed)

    @property
    def web(self) -> QWebEngineView:
        """Встроенный виджет веб-страницы (создаётся при первом обращении)."""
        self.ensure_loaded()
        assert self._web is not None
        return self._web

    @property
    def is_running(self) -> bool:
        """Выполняется ли сценарий прямо сейчас."""
        return self._adapter.is_running

    @property
    def theme(self) -> str:
        """Действующая тема Blockly (`dark`/`light`)."""
        return self._theme

    def set_theme(self, theme: str) -> None:
        """Сменить тему Blockly без перезагрузки страницы."""
        name = theme if theme in ("dark", "light") else "dark"
        if name == self._theme:
            return
        self._theme = name
        if self._web is not None:
            self._web.page().runJavaScript(
                f"window.editorApi && editorApi.setTheme({json.dumps(name)})"
            )

    def ensure_loaded(self) -> None:
        """Создать webview и загрузить страницу редактора (один раз)."""
        if self._web is not None:
            return

        web = QWebEngineView(self)
        page = _EditorPage(web)
        web.setPage(page)

        channel = QWebChannel(web)
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

        layout = self.layout()
        assert layout is not None
        layout.addWidget(web)
        self._web = web
        url = QUrl.fromLocalFile(str(resource_path("blockly", "index.html")))
        # Тема и хоткеи в хэше: страница выбирает тему до инъекции Blockly —
        # при светлой теме нет вспышки тёмного холста, а подсказки кнопок
        # сразу показывают пользовательские сочетания.
        url.setFragment(
            urlencode(
                {
                    "theme": self._theme,
                    "start": self._hotkey_start,
                    "stop": self._hotkey_stop,
                }
            )
        )
        web.load(url)
        logger.info("Страница редактора Blockly загружается (тема %s)", self._theme)

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802 — имя из Qt
        """Загрузить страницу при первом показе вкладки."""
        super().showEvent(event)
        # Дать раскладке выставить размер, чтобы Blockly стартовал не с нуля.
        QTimer.singleShot(0, self.ensure_loaded)

    def request_run(self) -> None:
        """Запустить сценарий по запросу (кнопка F5, мост).

        Workspace запрашивается у JS: перевод в IR и запуск выполняет мост.
        """
        if self._adapter.is_running:
            return
        self.ensure_loaded()
        self.web.page().runJavaScript(
            "window.__ckReady && editorApi.exportForRun ? "
            "editorApi.exportForRun() : null",
            self._on_export_for_run,
        )

    def request_stop(self) -> None:
        """Остановить сценарий (F6, кнопка «Стоп» в трее)."""
        self._bridge.stop()

    def set_hotkeys(self, start: str, stop: str) -> None:
        """Обновить подсказки кнопок «Запустить»/«Стоп» в тулбаре страницы."""
        self._hotkey_start = start
        self._hotkey_stop = stop
        self._bridge.set_stop_hotkey(stop)
        if self._web is None:
            return
        payload = json.dumps({"start": start, "stop": stop}, ensure_ascii=False)
        self._web.page().runJavaScript(
            f"window.editorApi && editorApi.setHotkeys({payload})"
        )

    def shutdown(self) -> None:
        """Остановить сценарий и снять нагрузку страницы."""
        self._adapter.stop(wait=True)
        if self._web is not None:
            self._web.stop()
            self._web.deleteLater()

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
