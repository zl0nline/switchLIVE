"""Консольный UI для оператора."""

from __future__ import annotations

import logging
import sys

from switchlive.app.discovery import run_discovery
from switchlive.core.credentials import Credentials


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


def _manual_credential_prompt(standard_creds: list[Credentials]) -> Credentials | None:
    """Запрос логина/пароля у оператора."""
    print()
    print("  ⚠️ Стандартные логины не подошли.")
    print("  Введите логин и пароль вручную:")
    try:
        username = input("  Логин: ").strip()
        password = input("  Пароль: ").strip()
        enable = input("  Enable password (пусто = нет): ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return None

    if not username:
        return None
    return Credentials(username=username, password=password, enable_password=enable)


def _handle_discovery() -> None:
    """Запуск автопоиска коммутатора."""
    print("\n  🔍 Поиск коммутатора...\n")

    def progress(msg: str) -> None:
        print(f"  {msg}")

    result = run_discovery(
        standard_logins_path="standart_login.txt",
        manual_credential_callback=_manual_credential_prompt,
        progress_callback=progress,
    )

    print()
    if result.found and result.identity:
        ident = result.identity
        print("  ✅ Устройство найдено!")
        print(f"     Вендор:   {ident.vendor}")
        print(f"     Модель:    {ident.model}")
        print(f"     Серийник:  {ident.serial}")
        print(f"     Прошивка:  {ident.firmware}")
        print(f"     Порт:      {result.port}")
        print(f"     Авторизация: {result.auth_method}")
    elif result.error:
        print(f"  ❌ {result.error}")
    else:
        print("  ❌ Устройство не найдено")


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
            _handle_discovery()
        elif choice == "2":
            _handle_test_menu()
        elif choice == "3":
            print("\n  ⚠️ История — ещё не реализовано (issue #14)\n")
        elif choice == "4":
            print("\n  ⚠️ Настройки — ещё не реализовано\n")
        else:
            print("\n  ❌ Неизвестная команда\n")


def _handle_test_menu() -> None:
    """Меню тестирования."""
    from switchlive.app.traffic_iperf import (
        check_iperf3_available,
        check_server_reachable,
    )

    print("\n  ▶️  Тестирование\n")
    print("  iperf3 трафик-тест:")

    # Проверка iperf3
    if not check_iperf3_available():
        print("  ❌ iperf3 не установлен. Установите: apt install iperf3")
        return

    print("  ✅ iperf3 найден")

    # IP сервера
    server_ip = input("  IP iperf-сервера (пусто = без трафик-теста): ").strip()
    if not server_ip:
        print("  ℹ️  Трафик-тест пропущен\n")
        return

    # Проверка доступности
    server_port = 5201
    print(f"  Проверка {server_ip}:{server_port}...", end=" ")
    if check_server_reachable(server_ip, server_port):
        print("✅ хост обнаружен")
    else:
        print("❌ недоступен")
        print("  ⚠️  Проверьте IP и запущен ли iperf3 -s на сервере\n")
        return

    print()
    print("  ⚠️ Walk-test с iperf пока запускается из API.")
    print("  Конфигурация принята. Полная интеграция UI в следующем PR.\n")


if __name__ == "__main__":
    show_start_menu()
    sys.exit(0)
