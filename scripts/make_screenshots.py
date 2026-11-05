"""Снимки интерфейса для README: offscreen-рендер реального окна.

Скрипт поднимает настоящее окно ClicKit в offscreen-режиме (без экрана),
заполняет форму демонстрационными значениями и сохраняет PNG в `docs/img/`.
Ввод не эмулируется: используется mock-бэкенд, поэтому мышь не двигается,
а пользовательские настройки в `%APPDATA%` не читаются и не пишутся.

Запуск из корня репозитория:

    python scripts/make_screenshots.py

QtWebEngine должен уметь запуститься без GPU и sandbox — это те же
переменные окружения, что и в CI/смоук-тестах.
"""

import os
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

# Переменные Qt нужно выставить до импорта PySide6.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUTPUT_DIR = ROOT / "docs" / "img"
WINDOW_SIZE = (1160, 720)


class RenderBackend:
    """Mock-бэкенд ввода: ничего не отправляет (скриншот не двигает мышь)."""

    def position(self) -> tuple[int, int]:
        """Позиция курсора для пикера (значение не используется)."""
        return (0, 0)

    def click(self, x: int, y: int, button: object = None) -> None:
        """Заглушка одиночного клика."""

    def double_click(self, x: int, y: int, button: object = None) -> None:
        """Заглушка двойного клика."""

    def move_to(self, x: int, y: int, duration: float = 0.0) -> None:
        """Заглушка перемещения курсора."""

    def drag_to(
        self,
        x: int,
        y: int,
        duration: float = 0.5,
        button: object = None,
    ) -> None:
        """Заглушка перетаскивания."""

    def press_key(self, keys: str) -> None:
        """Заглушка нажатия клавиши."""

    def scroll(self, amount: int, x: int | None = None, y: int | None = None) -> None:
        """Заглушка прокрутки."""


def _pump(app: object, milliseconds: int) -> None:
    """Прокрутить цикл событий Qt на заданное время (для отрисовки)."""
    from PySide6.QtCore import QEventLoop, QTimer

    loop = QEventLoop()
    QTimer.singleShot(milliseconds, loop.quit)
    loop.exec()
    app.processEvents()  # type: ignore[attr-defined] — QApplication.processEvents


def _wait_for(app: object, predicate: Callable[[], bool], timeout_ms: int) -> bool:
    """Дождаться выполнения `predicate`, прокручивая события."""
    waited = 0
    while waited < timeout_ms:
        if predicate():
            return True
        _pump(app, 100)
        waited += 100
    return predicate()


def _grab(window: object, path: Path) -> None:
    """Сохранить снимок виджета в PNG."""
    path.parent.mkdir(parents=True, exist_ok=True)
    pixmap = window.grab()  # type: ignore[attr-defined] — QWidget.grab
    if not pixmap.save(str(path)):
        raise RuntimeError(f"не удалось сохранить снимок: {path}")
    print(f"  сохранён {path.relative_to(ROOT)} ({pixmap.width()}×{pixmap.height()})")


def main() -> int:
    """Сделать снимки простого режима и редактора сценариев."""
    from PySide6.QtWidgets import QApplication, QTabWidget

    from core.settings import Settings, SettingsStore
    from gui.main_window import MainWindow
    from gui.theme import ThemeManager

    app = QApplication.instance() or QApplication(sys.argv)

    settings = Settings(
        x=960,
        y=540,
        button="left",
        interval_ms=100,
        repeats=100,
        theme="dark",
    )
    with tempfile.TemporaryDirectory(prefix="clickit-shots-") as appdata:
        store = SettingsStore(Path(appdata) / "ClicKit" / "settings.json")
        theme = ThemeManager("dark")
        theme.apply(app)
        window = MainWindow(
            settings=settings,
            store=store,
            backend=RenderBackend(),  # type: ignore[arg-type] — duck typing
            enable_hotkeys=False,
            theme=theme,
        )
        window.resize(*WINDOW_SIZE)
        window.show()
        _pump(app, 500)

        print("Снимок «Простой режим»…")
        _grab(window, OUTPUT_DIR / "screenshot-simple-mode.png")

        tabs = window.findChild(QTabWidget)
        if tabs is not None and tabs.count() > 1:
            print("Снимок «Редактор сценариев»…")
            tabs.setCurrentIndex(1)
            _pump(app, 300)

            editor = tabs.widget(1)
            web = editor.web  # type: ignore[attr-defined] — EditorView
            state = {"ready": False}

            def on_check(value: object) -> None:
                state["ready"] = bool(value)

            def is_ready() -> bool:
                web.page().runJavaScript("Boolean(window.__ckReady)", on_check)
                return state["ready"]

            if _wait_for(app, is_ready, 15_000):
                # Дать Blockly разложить стартовый сценарий и дорисовать холст.
                _pump(app, 1500)
            else:
                print("  редактор не успел загрузиться — снимок без Blockly")
            _grab(window, OUTPUT_DIR / "screenshot-editor.png")

    print("Готово.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
