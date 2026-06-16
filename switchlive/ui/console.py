"""Консольный UI для оператора."""

from __future__ import annotations

import logging
import sys


def _print_menu() -> None:
    print()
    print("=" * 50)
    print("  switchLIVE — тестирование коммутаторов")
    print("=" * 50)
    print()
    print("  1. 🔍 Определение коммутатора")
    print("  2. ▶️  Начать тестирование")
    print("  3. 📋 История тестов")
    print("  4. ⚙️  Настройки")
    print("  0. 🚪 Выход")
    print()


def show_start_menu() -> None:
    """Показать стартовое меню."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    _print_menu()

    while True:
        try:
            choice = input("  Выберите действие: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if choice == "0":
            print("  До свидания!")
            break
        elif choice == "1":
            print("\n  ⚠️ Определение коммутатора — ещё не реализовано (issue #5)\n")
        elif choice == "2":
            print("\n  ⚠️ Тестирование — ещё не реализовано (issue #8)\n")
        elif choice == "3":
            print("\n  ⚠️ История — ещё не реализовано (issue #14)\n")
        elif choice == "4":
            print("\n  ⚠️ Настройки — ещё не реализовано\n")
        else:
            print("\n  ❌ Неизвестная команда\n")


if __name__ == "__main__":
    show_start_menu()
    sys.exit(0)
