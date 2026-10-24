"""Консольное демо M1: N кликов в точку, F5 — старт, F6 — стоп, Esc — выход.

Пример запуска:
    python scripts/demo_click.py --x 1000 --y 500 --count 100 --interval 0.1
"""

import argparse
import logging
import sys
import threading
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.executor import Command, CommandType, Executor  # noqa: E402
from core.hotkeys import HotkeyManager  # noqa: E402
from core.input.backend import Button, create_backend  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Разобрать аргументы командной строки."""
    parser = argparse.ArgumentParser(description="Демо автокликера ClicKit (M1)")
    parser.add_argument("--x", type=int, required=True, help="координата X экрана")
    parser.add_argument("--y", type=int, required=True, help="координата Y экрана")
    parser.add_argument("--count", type=int, default=100, help="число кликов")
    parser.add_argument(
        "--interval",
        type=float,
        default=0.1,
        help="интервал между кликами, секунды",
    )
    parser.add_argument(
        "--button",
        choices=[button.value for button in Button],
        default=Button.LEFT.value,
        help="кнопка мыши",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Точка входа демо-скрипта."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = parse_args(argv)
    button = Button(args.button)

    def on_step(steps: int) -> None:
        if steps >= args.count:
            print(f"\rКлики: {steps}/{args.count} — готово")
        else:
            print(f"\rКлики: {steps}/{args.count}", end="", flush=True)

    commands = [Command(CommandType.CLICK, x=args.x, y=args.y, button=button)]
    executor = Executor(
        create_backend(),
        commands,
        interval=args.interval,
        repeats=args.count,
        on_step=on_step,
    )

    exit_event = threading.Event()
    hotkeys = HotkeyManager()
    hotkeys.register("<f5>", executor.start)
    hotkeys.register("<f6>", executor.stop)
    hotkeys.register("<esc>", exit_event.set)
    hotkeys.start()

    print(
        f"Клик в ({args.x}, {args.y}), кнопка: {button.value}, "
        f"повторов: {args.count}, интервал: {args.interval} с"
    )
    print("F5 — старт, F6 — стоп, Esc — выход")

    try:
        while not exit_event.wait(0.1):
            pass
    except KeyboardInterrupt:
        pass
    finally:
        executor.stop()
        hotkeys.stop()
        print("\nВыход.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
