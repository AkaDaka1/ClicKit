"""Смоук-тесты страницы редактора на QtWebEngine (offscreen).

Тест медленный и зависит от Chromium; в средах без WebEngine его можно
отключить переменной окружения `CLICKIT_SKIP_WEB=1`.
"""

import json
import os
import time

import pytest
from PySide6.QtWidgets import QApplication

from gui.editor.editor_view import EditorView
from tests.test_executor import MockBackend

pytestmark = pytest.mark.skipif(
    os.environ.get("CLICKIT_SKIP_WEB") == "1",
    reason="QtWebEngine отключён переменной CLICKIT_SKIP_WEB",
)


def eval_js(view: EditorView, expression: str, timeout: float = 20.0) -> object:
    """Выполнить JS и дождаться результата, прокачивая очередь событий Qt."""
    holder: dict[str, object] = {"done": False, "value": None}

    def callback(value: object) -> None:
        holder["value"] = value
        holder["done"] = True

    view.web.page().runJavaScript(expression, callback)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and not holder["done"]:
        QApplication.processEvents()
        time.sleep(0.01)
    if not holder["done"]:
        raise AssertionError(f"JS не ответил за {timeout:g} с: {expression}")
    return holder["value"]


def wait_js(view: EditorView, expression: str, timeout: float = 20.0) -> bool:
    """Ждать, пока JS-выражение не вернёт истину."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if eval_js(view, expression, timeout=2.0) is True:
            return True
        time.sleep(0.05)
    return False


def close_view(view: EditorView) -> None:
    """Аккуратно уничтожить webview (иначе Windows/Chromium падает на выходе)."""
    view.shutdown()
    view.close()
    view.deleteLater()
    QApplication.processEvents()


def test_page_loads_and_has_starter_blocks(qt_app: object) -> None:
    """Страница загружается, Blockly готов и стартовый сценарий на месте."""
    view = EditorView(MockBackend())
    view.resize(1000, 700)
    view.show()
    try:
        assert wait_js(view, "window.__ckReady === true")
        assert wait_js(view, "window.__ckChannelReady === true")

        stats = json.loads(eval_js(view, "editorApi.getWorkspaceStats()"))
        assert stats["blocks"] >= 4
        assert stats["name"] == "Пример"
        assert stats["running"] is False
        assert stats["dirty"] is False
        assert eval_js(view, "document.title.indexOf('Пример') >= 0") is True
    finally:
        close_view(view)


def test_export_for_run_returns_workspace(qt_app: object) -> None:
    """F5-экспорт отдаёт имя и валидный Blockly-JSON."""
    view = EditorView(MockBackend())
    view.resize(1000, 700)
    view.show()
    try:
        assert wait_js(view, "window.__ckReady === true")
        payload = eval_js(view, "editorApi.exportForRun()")
        assert isinstance(payload, str)
        data = json.loads(payload)
        assert data["name"] == "Пример"
        blocks = data["workspace"]["blocks"]["blocks"]
        assert blocks
        assert blocks[0]["type"] == "ck_click"
    finally:
        close_view(view)


def test_highlight_marks_block(qt_app: object) -> None:
    """Подсветка добавляет CSS-класс выполняемому блоку."""
    view = EditorView(MockBackend())
    view.resize(1000, 700)
    view.show()
    try:
        assert wait_js(view, "window.__ckReady === true")
        marked = eval_js(
            view,
            "(() => {"
            "  editorApi.highlightBlock('starter-loop');"
            "  return document.querySelector('.ck-running') !== null;"
            "})()",
        )
        assert marked is True

        cleared = eval_js(
            view,
            "(() => {"
            "  editorApi.clearHighlight();"
            "  return document.querySelector('.ck-running') === null;"
            "})()",
        )
        assert cleared is True
    finally:
        close_view(view)


def test_request_run_executes_starter_scenario(qt_app: object) -> None:
    """F5-путь: Python просит workspace у JS, сценарий выполняется и завершается."""
    backend = MockBackend()
    view = EditorView(backend)
    view.resize(1000, 700)
    view.show()
    try:
        assert wait_js(view, "window.__ckReady === true")
        assert wait_js(view, "window.__ckChannelReady === true")

        view.request_run()

        def running() -> bool:
            stats = json.loads(eval_js(view, "editorApi.getWorkspaceStats()"))
            return bool(stats["running"])

        deadline = time.monotonic() + 10
        started = False
        while time.monotonic() < deadline:
            if running():
                started = True
                break
            time.sleep(0.05)
        assert started, "Сценарий не перешёл в состояние «выполняется»"

        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if not running():
                break
            time.sleep(0.05)
        assert not running(), "Сценарий не завершился"

        status = eval_js(view, "document.getElementById('status').textContent")
        assert isinstance(status, str) and "Сценарий" in status
        assert backend.calls, "Сценарий не выполнил ни одного действия"
    finally:
        close_view(view)
