"""Тесты консольного запуска сценария (`scripts/run_scenario.py`)."""

import json
from pathlib import Path

import pytest

import scripts.run_scenario as cli
from core.input.backend import Button
from core.ir.schema import scenario_from_mapping
from core.ir.storage import load_scenario
from tests.test_executor import MockBackend

#: Пример сценария из ресурсов — он же используется в документации.
SAMPLE = (
    Path(__file__).resolve().parents[1]
    / "resources"
    / "examples"
    / "click_pause_loop.acl.json"
)


def test_parse_args() -> None:
    """Флаги dry-run, no-hotkeys и verbose разбираются."""
    args = cli.parse_args(["file.acl.json", "--dry-run", "--no-hotkeys", "-v"])

    assert args.scenario == Path("file.acl.json")
    assert args.dry_run
    assert args.no_hotkeys
    assert args.verbose


def test_dry_run_sample(capsys: pytest.CaptureFixture[str]) -> None:
    """Пример проходит проверку и даёт 22 действия без ввода."""
    code = cli.main([str(SAMPLE), "--dry-run"])

    captured = capsys.readouterr()
    assert code == 0
    assert "Действий в сценарии: 22" in captured.out
    assert "Запуск не выполнялся" in captured.out


def test_dry_run_invalid_scenario(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Невалидный сценарий — код 2 и список ошибок."""
    path = tmp_path / "bad.acl.json"
    path.write_text(
        json.dumps({"version": 1, "nodes": [{"type": "nope"}]}),
        encoding="utf-8",
    )

    code = cli.main([str(path), "--dry-run"])

    captured = capsys.readouterr()
    assert code == 2
    assert "не прошёл проверку" in captured.err
    assert "неизвестный тип" in captured.err


def test_dry_run_broken_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Битый JSON — код 2 без трассировки."""
    path = tmp_path / "broken.acl.json"
    path.write_text("{", encoding="utf-8")

    code = cli.main([str(path), "--dry-run"])

    captured = capsys.readouterr()
    assert code == 2
    assert "JSON" in captured.err


def test_missing_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Отсутствующий файл — код 1 и понятное сообщение."""
    code = cli.main([str(tmp_path / "missing.acl.json"), "--dry-run"])

    captured = capsys.readouterr()
    assert code == 1
    assert "Не удалось прочитать" in captured.err


def test_execute_runs_scenario(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Реальный прогон через CLI выполняет сценарий на бэкенде."""
    backend = MockBackend()
    monkeypatch.setattr(cli, "create_backend", lambda: backend)

    code = cli._execute(load_scenario(SAMPLE), "проверка", no_hotkeys=True)

    captured = capsys.readouterr()
    assert code == 0
    assert "Сценарий выполнен." in captured.out
    # 22 действия, но пауза не вызывает бэкенд — 21 запись.
    assert len(backend.calls) == 21


def test_execute_reports_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Ошибка бэкенда — код 1 и сообщение с путём узла."""

    class BrokenBackend(MockBackend):
        def click(self, x: int, y: int, button: Button = Button.LEFT) -> None:
            raise RuntimeError("нет связи")

    monkeypatch.setattr(cli, "create_backend", lambda: BrokenBackend())
    scenario = scenario_from_mapping(
        {"version": 1, "nodes": [{"type": "click", "x": 1, "y": 1}]}
    )

    code = cli._execute(scenario, "проверка", no_hotkeys=True)

    captured = capsys.readouterr()
    assert code == 1
    assert "Ошибка исполнения" in captured.err
    assert "nodes[0]" in captured.err
