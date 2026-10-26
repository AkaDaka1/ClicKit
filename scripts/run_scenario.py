"""Консольный запуск IR-сценария ClicKit (M3).

Примеры:
    python scripts/run_scenario.py resources/examples/click_pause_loop.acl.json
    python scripts/run_scenario.py <файл> --dry-run
"""

import argparse
import logging
import sys
import threading
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.hotkeys import HotkeyManager  # noqa: E402
from core.input.backend import create_backend  # noqa: E402
from core.ir.interpreter import Interpreter  # noqa: E402
from core.ir.nodes import Scenario  # noqa: E402
from core.ir.schema import ScenarioValidationError  # noqa: E402
from core.ir.storage import ScenarioFileError, load_scenario  # noqa: E402
from core.scenario_runner import ScenarioRunner  # noqa: E402
from core.worker import StopReason  # noqa: E402

#: Коды выхода скрипта.
EXIT_OK = 0
EXIT_RUNTIME = 1
EXIT_INVALID = 2


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Разобрать аргументы командной строки."""
    parser = argparse.ArgumentParser(
        description="Запуск сценария ClicKit из файла .acl.json"
    )
    parser.add_argument("scenario", type=Path, help="путь к файлу .acl.json")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="проверить сценарий и посчитать действия, не выполняя ввод",
    )
    parser.add_argument(
        "--no-hotkeys",
        action="store_true",
        help="не регистрировать глобальные хоткеи (стоп — Ctrl+C)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="подробный журнал (трассировки ошибок)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Точка входа: загрузить сценарий и выполнить его до конца или стопа."""
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.CRITICAL,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    try:
        scenario = load_scenario(args.scenario)
    except ScenarioFileError as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return EXIT_RUNTIME
    except ScenarioValidationError as exc:
        print("Сценарий не прошёл проверку:", file=sys.stderr)
        for issue in exc.issues:
            print(f"  {issue.path}: {issue.message}", file=sys.stderr)
        return EXIT_INVALID

    title = scenario.name or args.scenario.name
    if args.dry_run:
        print(f"Сценарий: {title}")
        interpreter = Interpreter(create_backend(), scenario, dry_run=True)
        steps = interpreter.run()
        print(f"Проверка пройдена. Действий в сценарии: {steps}")
        print("Запуск не выполнялся (--dry-run).")
        return EXIT_OK

    return _execute(scenario, title, no_hotkeys=args.no_hotkeys)


def _execute(scenario: Scenario, title: str, no_hotkeys: bool) -> int:
    """Выполнить сценарий с горячими клавишами и напечатать итог."""
    result: dict[str, object] = {"reason": None, "detail": ""}
    finished = threading.Event()

    def on_finish(reason: StopReason, detail: str) -> None:
        result["reason"] = reason
        result["detail"] = detail
        finished.set()

    def on_step(count: int) -> None:
        print(f"\rДействие: {count}", end="", flush=True)

    runner = ScenarioRunner(
        create_backend(),
        scenario,
        on_step=on_step,
        on_finish=on_finish,
    )
    hotkeys: HotkeyManager | None = None
    if not no_hotkeys:
        hotkeys = HotkeyManager()
        hotkeys.register("<f6>", runner.stop)
        hotkeys.register("<esc>", finished.set)
        hotkeys.start()

    print(f"Сценарий: {title}")
    print("F6 — стоп, Esc — выход" if hotkeys else "Ctrl+C — стоп")
    runner.start()
    try:
        while not finished.wait(0.1):
            pass
    except KeyboardInterrupt:
        runner.stop()
    finally:
        runner.stop()
        runner.join(timeout=2.0)
        if hotkeys is not None:
            hotkeys.stop()
        print()

    reason = result["reason"]
    detail = str(result["detail"] or "")
    if reason is StopReason.COMPLETED:
        print("Сценарий выполнен.")
        return EXIT_OK
    if reason is StopReason.STOPPED or reason is None:
        print("Остановлено.")
        return EXIT_OK
    if reason is StopReason.FAILSAFE:
        print(f"Сработала защита: {detail or 'курсор в углу экрана'}")
        return EXIT_RUNTIME
    if reason is StopReason.ERROR:
        print(f"Ошибка исполнения: {detail}", file=sys.stderr)
        return EXIT_RUNTIME
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
