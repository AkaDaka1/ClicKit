"""Тесты журналирования: файл, ротация, UTF-8, перехват исключений."""

import logging
import sys
import threading
from collections.abc import Iterator
from logging.handlers import RotatingFileHandler
from pathlib import Path

import pytest

from app import logging_setup


@pytest.fixture
def journal(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Path]:
    """Настроенный журнал во временном `%APPDATA%` с очисткой после теста."""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    path = logging_setup.setup_logging()
    yield path
    root = logging.getLogger()
    for handler in list(root.handlers):
        if getattr(handler, "_clickit_handler", False):
            root.removeHandler(handler)
            handler.close()


def flush_handlers() -> None:
    """Сбросить буферы всех обработчиков корневого логгера."""
    for handler in logging.getLogger().handlers:
        handler.flush()


def test_log_file_is_created_and_written(journal: Path) -> None:
    """Журнал пишется в `%APPDATA%\\ClicKit\\logs\\app.log` в UTF-8."""
    logging.getLogger("clickit.test").info("Проверка журнала: клик выполнен")
    flush_handlers()

    assert journal.name == "app.log"
    assert journal.parent == Path(logging_setup.log_dir())
    text = journal.read_text(encoding="utf-8")
    assert "Проверка журнала: клик выполнен" in text
    assert "INFO" in text


def test_file_handler_has_rotation(journal: Path) -> None:
    """Файловый обработчик настроен на ротацию 1 МБ × 3."""
    handlers = [
        handler
        for handler in logging.getLogger().handlers
        if isinstance(handler, RotatingFileHandler)
    ]

    assert len(handlers) == 1
    assert handlers[0].maxBytes == logging_setup.LOG_MAX_BYTES
    assert handlers[0].backupCount == logging_setup.LOG_BACKUP_COUNT
    assert handlers[0].encoding == "utf-8"


def test_setup_is_idempotent(journal: Path) -> None:
    """Повторная настройка не плодит обработчики ClicKit."""
    root = logging.getLogger()
    before = sum(
        1 for handler in root.handlers if getattr(handler, "_clickit_handler", False)
    )

    logging_setup.setup_logging()

    after = sum(
        1 for handler in root.handlers if getattr(handler, "_clickit_handler", False)
    )
    assert after == before


def test_uncaught_exception_is_logged(
    journal: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Необработанная ошибка пишется в журнал как CRITICAL с traceback."""
    notified: list[bool] = []
    monkeypatch.setattr(logging_setup, "_notify_user", lambda: notified.append(True))
    previous_sys = sys.excepthook
    previous_thread = threading.excepthook
    try:
        logging_setup.install_excepthook()
        try:
            raise ValueError("сломалось насовсем")
        except ValueError:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            sys.excepthook(exc_type, exc_value, exc_traceback)
    finally:
        sys.excepthook = previous_sys
        threading.excepthook = previous_thread
    flush_handlers()

    text = journal.read_text(encoding="utf-8")
    assert "Необработанная ошибка" in text
    assert "ValueError: сломалось насовсем" in text
    assert "Traceback" in text
    assert notified == [True]


def test_thread_exception_is_logged(
    journal: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ошибка в фоновом потоке тоже попадает в журнал."""
    monkeypatch.setattr(logging_setup, "_notify_user", lambda: None)
    args = threading.ExceptHookArgs(
        (RuntimeError, RuntimeError("в потоке"), None, None)
    )

    logging_setup._handle_thread_uncaught(args)
    flush_handlers()

    text = journal.read_text(encoding="utf-8")
    assert "в потоке" in text
    assert "Необработанная ошибка в потоке" in text


def test_log_dir_uses_appdata(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Каталог журналов находится в `%APPDATA%\\ClicKit\\logs`."""
    monkeypatch.setenv("APPDATA", str(tmp_path))

    assert logging_setup.log_dir() == tmp_path / "ClicKit" / "logs"
    assert logging_setup.log_path() == tmp_path / "ClicKit" / "logs" / "app.log"
