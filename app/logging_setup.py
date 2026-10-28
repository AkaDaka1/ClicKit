"""Логирование ClicKit: файл с ротацией, UTF-8-консоль, дружелюбные ошибки."""

from __future__ import annotations

import logging
import os
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path
from types import TracebackType

LOG_FILENAME = "app.log"
LOG_MAX_BYTES = 1_048_576
LOG_BACKUP_COUNT = 3
LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"

#: Пометка «наш» обработчик, чтобы не трогать чужие (например, pytest).
_APP_HANDLER_MARK = "_clickit_handler"

#: Защита от лавины диалогов об ошибках за один запуск.
_crash_dialog_shown = False


def log_dir() -> Path:
    """Каталог журналов: `%APPDATA%\\ClicKit\\logs` (запасной — `~/.config`)."""
    appdata = os.environ.get("APPDATA")
    base = Path(appdata) if appdata else Path.home() / ".config"
    return base / "ClicKit" / "logs"


def log_path() -> Path:
    """Путь к файлу журнала `app.log`."""
    return log_dir() / LOG_FILENAME


def setup_logging(level: int = logging.INFO) -> Path:
    """Настроить журналирование в файл и консоль; вернуть путь к файлу.

    Файл пишется в UTF-8 с ротацией (1 МБ × 3). Если каталог недоступен,
    приложение продолжает работать с консольным выводом. Повторный вызов
    заменяет только обработчики ClicKit, не затрагивая чужие.
    """
    root = logging.getLogger()
    root.setLevel(level)
    for handler in list(root.handlers):
        if getattr(handler, _APP_HANDLER_MARK, False):
            root.removeHandler(handler)
            handler.close()

    formatter = logging.Formatter(LOG_FORMAT)
    path = log_path()
    file_handler = _make_file_handler(path, formatter)
    if file_handler is not None:
        root.addHandler(file_handler)

    console = _make_console_handler(formatter)
    if console is not None:
        root.addHandler(console)
    return path


def _make_file_handler(
    path: Path, formatter: logging.Formatter
) -> RotatingFileHandler | None:
    """Файловый обработчик с ротацией; `None`, если каталог недоступен."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            path,
            maxBytes=LOG_MAX_BYTES,
            backupCount=LOG_BACKUP_COUNT,
            encoding="utf-8",
        )
    except OSError:
        logging.getLogger(__name__).warning(
            "Не удалось открыть журнал %s — пишем только в консоль",
            path,
            exc_info=True,
        )
        return None
    handler.setFormatter(formatter)
    setattr(handler, _APP_HANDLER_MARK, True)
    return handler


def _make_console_handler(formatter: logging.Formatter) -> logging.StreamHandler | None:
    """Консольный обработчик в UTF-8; в безоконной сборке консоли нет."""
    stream = sys.stderr
    if stream is None:
        return None
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is not None:
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):  # pragma: no cover — поток уже закрыт
            pass
    handler = logging.StreamHandler(stream)
    handler.setFormatter(formatter)
    setattr(handler, _APP_HANDLER_MARK, True)
    return handler


def install_excepthook() -> None:
    """Перехватывать необработанные исключения: журнал + понятное сообщение."""
    sys.excepthook = _handle_uncaught
    threading.excepthook = _handle_thread_uncaught


def _handle_uncaught(
    exc_type: type[BaseException],
    exc_value: BaseException,
    exc_traceback: TracebackType | None,
) -> None:
    """Необработанная ошибка в главном потоке."""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    logging.getLogger("clickit").critical(
        "Необработанная ошибка",
        exc_info=(exc_type, exc_value, exc_traceback),
    )
    _notify_user()


def _handle_thread_uncaught(args: threading.ExceptHookArgs) -> None:
    """Необработанная ошибка в фоновом потоке: только журнал, без диалога."""
    if args.exc_type is SystemExit:
        return
    thread_name = args.thread.name if args.thread is not None else "?"
    logging.getLogger("clickit").critical(
        "Необработанная ошибка в потоке %s",
        thread_name,
        exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
    )
    if threading.current_thread() is threading.main_thread():
        _notify_user()


def _notify_user() -> None:
    """Показать один раз за запуск диалог с путём к журналу."""
    global _crash_dialog_shown
    if _crash_dialog_shown:
        return

    try:
        from PySide6.QtWidgets import QApplication, QMessageBox
    except ImportError:  # pragma: no cover — PySide6 обязателен
        return
    if QApplication.instance() is None:
        return

    _crash_dialog_shown = True
    box = QMessageBox()
    box.setIcon(QMessageBox.Icon.Critical)
    box.setWindowTitle("ClicKit — непредвиденная ошибка")
    box.setText("ClicKit столкнулся с непредвиденной ошибкой.")
    box.setInformativeText(
        f"Подробности записаны в журнал:\n{log_path()}\n\n"
        "Перезапустите приложение. Если ошибка повторяется — "
        "пришлите файл журнала разработчику."
    )
    box.exec()


def reset_crash_dialog_state() -> None:
    """Сбросить флаг показа диалога (для тестов)."""
    global _crash_dialog_shown
    _crash_dialog_shown = False
