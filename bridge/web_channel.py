"""Мост QWebChannel между страницей Blockly и движком сценариев.

JS вызывает слоты (`run`, `stop`, `save`, `open`, …), Python отвечает
сигналами (`scenario_loaded`, `node_started`, `issues_found`, …). Слоты живут
в GUI-потоке: отсюда можно открывать диалоги файлов и запускать воркер.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtWidgets import QFileDialog, QWidget

from bridge.blockly_ir import (
    BlocklyIssue,
    BlocklyTranslationError,
    workspace_to_scenario,
)
from bridge.scenario_file import (
    load_document,
    resolve_workspace,
    save_document,
)
from core.ir.nodes import Scenario
from core.ir.schema import MAX_NAME_LENGTH, ScenarioValidationError
from core.ir.storage import (
    SCENARIO_SUFFIX,
    ScenarioFileError,
    default_scenarios_dir,
)
from core.worker import StopReason
from gui.editor.scenario_adapter import ScenarioAdapter

logger = logging.getLogger(__name__)

#: Диалог открытия: вернуть путь или `None` (отмена).
OpenDialog = Callable[[], str | None]
#: Диалог сохранения: предложенный путь → выбранный путь или `None`.
SaveDialog = Callable[[str], str | None]
#: Проверка, выполняется ли другой режим (простой автокликер).
BusyChecker = Callable[[], bool]

_OPEN_FILTER = "Сценарии ClicKit (*.acl.json);;JSON (*.json);;Все файлы (*)"
_SAVE_FILTER = "Сценарии ClicKit (*.acl.json);;JSON (*.json);;Все файлы (*)"
_INVALID_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


class ScenarioBridge(QObject):
    """Мост между JS-редактором и `ScenarioAdapter`."""

    # Python → JS
    scenario_loaded = Signal(str, str)  # имя, JSON workspace
    node_started = Signal(str)  # id блока
    step_done = Signal(int)  # выполнено действий
    run_finished = Signal(str, str)  # StopReason.value, понятное сообщение
    issues_found = Signal(str)  # JSON: [{"block_id": str|null, "message": str}]
    status_changed = Signal(str, bool)  # текст, ошибка?
    document_saved = Signal(str, str)  # путь, имя
    running_changed = Signal(bool)

    def __init__(
        self,
        adapter: ScenarioAdapter,
        open_dialog: OpenDialog | None = None,
        save_dialog: SaveDialog | None = None,
        dialog_parent: QWidget | None = None,
        is_busy_checker: BusyChecker | None = None,
        parent: QObject | None = None,
    ) -> None:
        """Создать мост.

        Args:
            adapter: адаптер сценария (общий бэкенд ввода).
            open_dialog: диалог открытия (в тестах подменяется).
            save_dialog: диалог сохранения (в тестах подменяется).
            dialog_parent: родитель модальных диалогов.
            is_busy_checker: проверка занятости другого режима (клики).
        """
        super().__init__(parent)
        self._adapter = adapter
        self._open_dialog = open_dialog if open_dialog is not None else self._ask_open
        self._save_dialog = save_dialog if save_dialog is not None else self._ask_save
        self._dialog_parent = dialog_parent
        self._is_busy_checker = is_busy_checker
        self._current_path: Path | None = None

        adapter.started.connect(self._on_started)
        adapter.step.connect(self.step_done)
        adapter.node_started.connect(self.node_started)
        adapter.finished.connect(self._on_finished)

    # --- слоты для JS --------------------------------------------------------

    @Slot(str, str)
    def run(self, name: str, workspace_json: str) -> None:
        """Собрать сценарий из блоков и запустить его."""
        if self._is_busy():
            self.status_changed.emit(
                "Другой режим уже выполняется — остановите его (F6)", True
            )
            return
        if self._adapter.is_running:
            self.status_changed.emit("Сценарий уже выполняется", False)
            return
        data = self._parse_workspace(workspace_json)
        if data is None:
            return
        scenario = self._scenario_from(data, name)
        if scenario is None:
            return
        if not self._adapter.start(scenario):
            self.status_changed.emit(
                "Не удалось начать выполнение — попробуйте ещё раз", True
            )

    @Slot()
    def stop(self) -> None:
        """Остановить сценарий (F6 или кнопка «Стоп»)."""
        if not self._adapter.is_running:
            return
        self._adapter.stop()
        self.status_changed.emit("Останавливаюсь…", False)

    @Slot(str, str)
    def save(self, name: str, workspace_json: str) -> None:
        """Сохранить сценарий (и состояние Blockly) в `.acl.json`."""
        data = self._parse_workspace(workspace_json)
        if data is None:
            return
        scenario = self._scenario_from(data, name)
        if scenario is None:
            return

        path = self._current_path
        if path is None:
            suggested = default_scenarios_dir() / (
                _safe_filename(scenario.name) + SCENARIO_SUFFIX
            )
            chosen = self._save_dialog(str(suggested))
            if not chosen:
                self.status_changed.emit("Сохранение отменено", False)
                return
            path = _ensure_suffix(Path(chosen))

        try:
            saved = save_document(scenario, path, data)
        except ScenarioFileError as exc:
            self.status_changed.emit(str(exc), True)
            return

        self._current_path = saved
        self.document_saved.emit(str(saved), scenario.name)
        self.status_changed.emit(f"Сохранено: {saved}", False)

    @Slot()
    def open(self) -> None:
        """Открыть `.acl.json` и восстановить блоки."""
        chosen = self._open_dialog()
        if not chosen:
            return
        path = Path(chosen)
        try:
            document = load_document(path)
        except ScenarioFileError as exc:
            self.status_changed.emit(str(exc), True)
            return
        except ScenarioValidationError as exc:
            self._report_issues(
                [
                    BlocklyIssue(None, f"{issue.path}: {issue.message}")
                    for issue in exc.issues
                ]
            )
            return

        try:
            workspace, restored = resolve_workspace(document)
        except BlocklyTranslationError as exc:
            self._report_issues(exc.issues)
            return

        self._current_path = path
        name = document.scenario.name or _display_name(path)
        self.scenario_loaded.emit(name, json.dumps(workspace, ensure_ascii=False))
        note = " (блоки восстановлены из IR)" if restored else ""
        self.status_changed.emit(f"Открыт сценарий: {path.name}{note}", False)

    @Slot()
    def new_document(self) -> None:
        """Начать новый сценарий: следующее сохранение спросит путь."""
        self._current_path = None
        self.status_changed.emit("Новый сценарий", False)

    @Slot()
    def ready(self) -> None:
        """Страница редактора загрузилась."""
        logger.info("Редактор Blockly готов")
        self.status_changed.emit("Редактор готов", False)

    @Slot(str)
    def log(self, message: str) -> None:
        """Сообщение из JS-консоли (для отладки)."""
        logger.info("JS: %s", message[:500])

    # --- события воркера -----------------------------------------------------

    def _on_started(self) -> None:
        """Сценарий начал выполняться."""
        self.running_changed.emit(True)
        self.status_changed.emit("Сценарий выполняется — остановить: F6", False)

    def _on_finished(self, reason_value: str, detail: str) -> None:
        """Сценарий завершился: сообщение, состояние кнопок, статус-бар."""
        try:
            reason = StopReason(reason_value)
        except ValueError:  # pragma: no cover — неизвестная причина из ядра
            reason = StopReason.ERROR
            detail = detail or reason_value

        message = self._finish_message(reason, detail)
        self.running_changed.emit(False)
        self.run_finished.emit(reason.value, message)
        self.status_changed.emit(message, reason is StopReason.ERROR)

    def _finish_message(self, reason: StopReason, detail: str) -> str:
        """Понятный текст по причине завершения."""
        if reason is StopReason.COMPLETED:
            return "Сценарий выполнен"
        if reason is StopReason.STOPPED:
            return "Сценарий остановлен"
        if reason is StopReason.FAILSAFE:
            return "Сработала защита: курсор в углу экрана — сценарий остановлен"
        return f"Ошибка: {detail}" if detail else "Ошибка выполнения"

    # --- разбор и проверка ---------------------------------------------------

    def _is_busy(self) -> bool:
        """Выполняется ли другой режим (простой автокликер)."""
        if self._is_busy_checker is None:
            return False
        return self._is_busy_checker()

    def _parse_workspace(self, workspace_json: str) -> dict[str, Any] | None:
        """Разобрать JSON из редактора; при ошибке — сообщение в JS."""
        try:
            data = json.loads(workspace_json)
        except json.JSONDecodeError:
            self._report_issues(
                [BlocklyIssue(None, "Редактор передал повреждённые данные")]
            )
            return None
        if not isinstance(data, dict):
            self._report_issues(
                [BlocklyIssue(None, "Редактор передал данные неверного формата")]
            )
            return None
        return data

    def _scenario_from(self, data: Mapping[str, Any], name: str) -> Scenario | None:
        """Транслировать блоки в IR; при ошибках — подсветка и статус."""
        try:
            result = workspace_to_scenario(data, _clean_name(name))
        except BlocklyTranslationError as exc:
            self._report_issues(exc.issues)
            return None
        if result.warnings:
            self.status_changed.emit(
                f"Отключённых блоков пропущено: {len(result.warnings)}", False
            )
        return result.scenario

    def _report_issues(self, issues: Sequence[BlocklyIssue]) -> None:
        """Отправить проблемы в JS для подсветки и показать первую в статусе."""
        payload = [
            {"block_id": issue.block_id, "message": issue.message} for issue in issues
        ]
        self.issues_found.emit(json.dumps(payload, ensure_ascii=False))
        first = issues[0].message if issues else "Не удалось собрать сценарий"
        suffix = f" (ещё {len(issues) - 1})" if len(issues) > 1 else ""
        self.status_changed.emit(first + suffix, True)

    # --- диалоги по умолчанию ------------------------------------------------

    def _ask_open(self) -> str | None:
        """Стандартный диалог открытия сценария."""
        path, _ = QFileDialog.getOpenFileName(
            self._dialog_parent,
            "Открыть сценарий",
            str(default_scenarios_dir()),
            _OPEN_FILTER,
        )
        return path or None

    def _ask_save(self, suggested: str) -> str | None:
        """Стандартный диалог сохранения сценария."""
        path, _ = QFileDialog.getSaveFileName(
            self._dialog_parent,
            "Сохранить сценарий",
            suggested,
            _SAVE_FILTER,
        )
        return path or None


def _clean_name(name: str) -> str:
    """Имя сценария: обрезать пробелы и длину, подставить дефолт."""
    cleaned = name.strip()[:MAX_NAME_LENGTH]
    return cleaned or "Сценарий"


def _safe_filename(name: str) -> str:
    """Безопасное имя файла для предложения в диалоге сохранения."""
    cleaned = _INVALID_FILENAME.sub("_", name).strip(" .")
    return cleaned[:80] or "scenario"


def _ensure_suffix(path: Path) -> Path:
    """Добавить `.acl.json`, если пользователь не указал расширение."""
    lowered = path.name.lower()
    if lowered.endswith(SCENARIO_SUFFIX) or lowered.endswith(".json"):
        return path
    return path.with_name(path.name + SCENARIO_SUFFIX)


def _display_name(path: Path) -> str:
    """Имя сценария из имени файла без расширения."""
    name = path.name
    for suffix in (SCENARIO_SUFFIX, ".json"):
        if name.lower().endswith(suffix):
            return name[: -len(suffix)]
    return name
