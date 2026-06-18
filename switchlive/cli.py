"""Точка входа CLI."""

import argparse
import subprocess
import sys
from pathlib import Path

from switchlive.app.console_probe import (
    baudrates_from_config,
    format_probe_report,
    parse_baudrates,
    probe_console,
    write_probe_samples,
)
from switchlive.config import Config
from switchlive.diagnostics import collect_debug_bundle, configure_logging
from switchlive.ui.console import show_start_menu


def main(argv: list[str] | None = None) -> int:
    """Запуск главного меню."""
    args = _parse_args(argv)
    if args.command == "update":
        return run_update()

    config = Config.load(args.config)
    if args.debug:
        config.debug = True
    context = configure_logging(debug=config.debug)

    if args.bug_report:
        bundle = collect_debug_bundle(
            config=config,
            config_path=args.config,
            context=context,
        )
        print(f"Debug bundle: {bundle}")
        return 0

    if args.command == "console-probe":
        baudrates = parse_baudrates(args.baudrates) if args.baudrates else baudrates_from_config(config)
        results = probe_console(
            ports=args.port,
            baudrates=baudrates,
            timeout=args.timeout,
            wakeup=not args.no_wakeup,
        )
        print(format_probe_report(results))
        if args.output_dir:
            written = write_probe_samples(results, args.output_dir)
            if written:
                print("Saved samples:")
                for path in written:
                    print(f"- {path}")
        return 0

    show_start_menu(config=config, config_path=args.config, debug_context=context)
    return 0


def run_update(start: Path | None = None) -> int:
    """Update switchLIVE from its git checkout and reinstall through pipx."""
    root = _find_project_root(start or Path.cwd())
    if root is None:
        print("switchLIVE checkout not found. Run this command from the switchLIVE repo directory.")
        return 2

    for command in (["git", "pull"], ["pipx", "install", "--force", "."]):
        print(f"$ {' '.join(command)}")
        completed = subprocess.run(command, cwd=root, check=False)
        if completed.returncode != 0:
            return completed.returncode
    return 0


def _find_project_root(start: Path) -> Path | None:
    """Find local switchLIVE git checkout from current directory upward."""
    current = start.resolve()
    candidates = (current, *current.parents)
    for path in candidates:
        if not (path / ".git").exists():
            continue
        pyproject = path / "pyproject.toml"
        if pyproject.exists() and 'name = "switchlive"' in pyproject.read_text(encoding="utf-8"):
            return path
    return None


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="switchlive")
    parser.add_argument(
        "--config",
        default="switchlive.json",
        help="path to switchLIVE JSON config",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="enable verbose logging and write logs/switchlive-*.log",
    )
    parser.add_argument(
        "--bug-report",
        action="store_true",
        help="create a sanitized debug bundle and exit",
    )
    subparsers = parser.add_subparsers(dest="command")

    probe = subparsers.add_parser(
        "console-probe",
        help="probe serial console output across configured baudrates",
    )
    probe.add_argument(
        "--port",
        action="append",
        help="serial port to probe; can be passed multiple times; defaults to auto-detected USB serial ports",
    )
    probe.add_argument(
        "--baudrates",
        help="comma or space separated baudrates; defaults to serial.default_baudrates from config",
    )
    probe.add_argument(
        "--timeout",
        type=float,
        default=1.0,
        help="seconds to wait for output at each baudrate",
    )
    probe.add_argument(
        "--no-wakeup",
        action="store_true",
        help="do not send Enter before reading console output",
    )
    probe.add_argument(
        "--output-dir",
        help="write non-empty console samples to this directory",
    )
    subparsers.add_parser(
        "update",
        help="run git pull and reinstall switchLIVE with pipx",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    sys.exit(main())
