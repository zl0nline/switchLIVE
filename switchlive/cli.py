"""Точка входа CLI."""

import sys

from switchlive.ui.console import show_start_menu


def main() -> int:
    """Запуск главного меню."""
    show_start_menu()
    return 0


if __name__ == "__main__":
    sys.exit(main())
