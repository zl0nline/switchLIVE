"""Точка входа CLI."""

import argparse
import sys

from switchlive.config import Config
from switchlive.diagnostics import collect_debug_bundle, configure_logging
from switchlive.ui.console import show_start_menu


def main(argv: list[str] | None = None) -> int:
    """Запуск главного меню."""
    args = _parse_args(argv)
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

    show_start_menu(config=config, config_path=args.config, debug_context=context)
    return 0


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
    return parser.parse_args(argv)


if __name__ == "__main__":
    sys.exit(main())
