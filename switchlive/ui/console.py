"""Консольный UI для оператора."""

from __future__ import annotations

import re
import sys

from switchlive.app.discovery import run_discovery
from switchlive.app.traffic_iperf import (
    IperfConfig,
    check_iperf3_available,
    check_server_reachable,
)
from switchlive.app.walk_test import (
    PortTestResult,
    WalkTestConfig,
    WalkTestEngine,
    WalkTestState,
)
from switchlive.config import Config
from switchlive.core.credentials import Credentials
from switchlive.core.models import PortVerdict
from switchlive.core.timeouts import TimeoutPolicy
from switchlive.diagnostics import DebugContext, collect_debug_bundle, configure_logging

ANSI = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "dim": "\033[2m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "red": "\033[31m",
    "cyan": "\033[36m",
}


def _c(text: str, color: str) -> str:
    return f"{ANSI.get(color, '')}{text}{ANSI['reset']}"


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
    print("  5. 🧰 Собрать debug bundle")
    print("  0. 🚪 Выход")
    print()


def _print_bottom_menu() -> None:
    print()
    print("-" * 50)
    print("  Команды: 1 определить | 2 тест | 3 история | 4 настройки | 5 debug | 0 выход")
    print("-" * 50)
    print()


class _DiscoveryProgressPrinter:
    """Compact operator progress while debug log keeps full discovery details."""

    def __init__(self) -> None:
        self.total = 0
        self.checked = 0
        self.current_port = ""
        self._line_active = False

    def __call__(self, msg: str) -> None:
        if self._handle_compact(msg):
            return
        self.finish()
        print(f"  {_c('...', 'cyan')} {msg}")

    def finish(self) -> None:
        if self._line_active:
            sys.stdout.write("\r" + " " * 100 + "\r")
            sys.stdout.flush()
            self._line_active = False

    def _handle_compact(self, msg: str) -> bool:
        total_match = re.search(r"Найдено COM-портов:\s*(\d+)", msg)
        if total_match:
            self.total = int(total_match.group(1))
            self._render("поиск serial console")
            return True

        port_match = re.search(r"Проверка порта\s+(.+)\.\.\.", msg)
        if port_match:
            self.checked += 1
            self.current_port = port_match.group(1)
            self._render("проверка порта")
            return True

        quiet_fragments = (
            "Не удалось открыть",
            "Не удалось войти",
            "Нет ответа от консоли",
            "не распознано",
            "Зарегистрировано детекторов",
        )
        if any(fragment in msg for fragment in quiet_fragments):
            return True

        return False

    def _render(self, label: str) -> None:
        total = max(self.total, self.checked, 1)
        done = min(self.checked, total)
        bar = _progress_bar(done, total, width=16)
        port = f" {self.current_port}" if self.current_port else ""
        sys.stdout.write(f"\r  {bar} {label}{port}"[:100])
        sys.stdout.flush()
        self._line_active = True


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


def _handle_discovery(config: Config) -> None:
    """Запуск автопоиска коммутатора."""
    result = _run_discovery_wizard(config)

    print()
    if result.found and result.identity:
        _print_device_summary(result)
    elif result.error:
        print(_c(f"  [FAIL] {result.error}", "red"))
    else:
        print(_c("  [FAIL] Устройство не найдено", "red"))


def _run_discovery_wizard(config: Config):
    """Run discovery with operator-friendly progress."""
    print()
    _section("Определение коммутатора")

    progress = _DiscoveryProgressPrinter()
    try:
        return run_discovery(
            standard_logins_path=config.standard_login_file,
            manual_credential_callback=_manual_credential_prompt,
            progress_callback=progress,
        )
    finally:
        progress.finish()


def _print_device_summary(result) -> None:
    ident = result.identity
    print(_c("  [OK] Устройство найдено", "green"))
    print(f"     Вендор:       {ident.vendor}")
    print(f"     Модель:       {ident.model}")
    print(f"     Серийник:     {ident.serial}")
    print(f"     Прошивка:     {ident.firmware}")
    print(f"     Console порт: {result.port}")
    print(f"     Авторизация:  {result.auth_method}")


def show_start_menu(
    config: Config | None = None,
    config_path: str = "switchlive.json",
    debug_context: DebugContext | None = None,
) -> None:
    """Показать стартовое меню."""
    config = config or Config()
    debug_context = debug_context or configure_logging(debug=config.debug)

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
            _handle_discovery(config)
            _print_bottom_menu()
        elif choice == "2":
            _handle_test_menu(config)
            _print_bottom_menu()
        elif choice == "3":
            print("\n  ⚠️ Просмотр истории в консоли ещё не реализован\n")
            _print_bottom_menu()
        elif choice == "4":
            print("\n  ⚠️ Настройки — ещё не реализовано\n")
            _print_bottom_menu()
        elif choice == "5":
            _handle_debug_bundle(config, config_path, debug_context)
            _print_bottom_menu()
        else:
            print("\n  ❌ Неизвестная команда\n")
            _print_bottom_menu()


def _handle_debug_bundle(
    config: Config,
    config_path: str,
    debug_context: DebugContext,
) -> None:
    """Create a sanitized debug bundle for bug reports."""
    bundle = collect_debug_bundle(
        config=config,
        config_path=config_path,
        context=debug_context,
    )
    print()
    print(_c("  [OK] Debug bundle собран", "green"))
    print(f"     Файл: {bundle}")


def _handle_test_menu(config: Config) -> None:
    """Walk-test wizard."""
    _section("Мастер тестирования")
    discovery = _run_discovery_wizard(config)
    if not discovery.found or not discovery.adapter or not discovery.session:
        print(_c("  [FAIL] Сначала не удалось определить устройство", "red"))
        return

    _print_device_summary(discovery)
    adapter = discovery.adapter
    session = discovery.session
    ports = adapter.list_ports(session)
    print()
    print(f"  Профиль теста: {len(ports)} портов, vendor adapter: {type(adapter).__name__}")
    if not _confirm("  Запустить walk-test по этому профилю?", default=True):
        print("  Тест отменён оператором.")
        return

    test_config = _configure_walk_test(config)
    engine = WalkTestEngine(adapter, session, test_config)

    _section("Ход тестирования")
    results = engine.run(
        ports=ports,
        progress_callback=_make_walk_progress(len(ports)),
    )

    _print_walk_summary(results)


def _configure_walk_test(config: Config | None = None) -> WalkTestConfig:
    """Collect walk-test settings from operator."""
    config = config or Config()
    print()
    print(_c("  Настройка дополнительных тестов", "bold"))

    iperf_config = None
    run_traffic = False
    if check_iperf3_available():
        server_ip = _input_with_default(
            "  IP iperf-сервера",
            config.iperf_server_host or "",
            empty_hint="пропустить",
        )
        if server_ip:
            server_port = config.iperf_server_port
            print(f"  Проверка {server_ip}:{server_port}...", end=" ")
            if check_server_reachable(server_ip, server_port):
                print(_c("[OK]", "green"))
                run_traffic = True
                iperf_config = IperfConfig(
                    server_host=server_ip,
                    server_port=server_port,
                    duration_sec=config.iperf_duration,
                    min_throughput_mbps=config.iperf_min_throughput_mbps,
                    max_loss_percent=config.iperf_max_loss_percent,
                )
            else:
                print(_c("[WARN]", "yellow"))
                print("  iperf пропущен: сервер недоступен или iperf3 -s не запущен.")
    else:
        print(_c("  [WARN] iperf3 не найден, трафик-тест будет пропущен.", "yellow"))

    poe_camera_ip = input("  IP PoE-камеры (Enter = проверять только питание): ").strip()

    return WalkTestConfig(
        timeout_policy=TimeoutPolicy(
            base=config.link_timeout_sec,
            poe=config.poe_timeout_sec,
            max=config.max_timeout_sec,
        ),
        run_traffic=run_traffic,
        iperf_config=iperf_config,
        poe_camera_ip=poe_camera_ip,
    )


def _input_with_default(prompt: str, default: str, empty_hint: str = "") -> str:
    """Read input and use config default when present."""
    if default:
        answer = input(f"{prompt} [{default}]: ").strip()
        return answer or default
    suffix = f" (Enter = {empty_hint})" if empty_hint else ""
    return input(f"{prompt}{suffix}: ").strip()


def _make_walk_progress(total_ports: int):
    tested = 0

    def progress(state: WalkTestState, msg: str) -> None:
        nonlocal tested
        if state == WalkTestState.NEXT_PORT:
            tested += 1
        prefix = _state_prefix(state)
        bar = _progress_bar(tested, total_ports)
        print(f"  {bar} {prefix} {msg}")

    return progress


def _print_walk_summary(results: list[PortTestResult]) -> None:
    _section("Итог")
    counts = {verdict: 0 for verdict in PortVerdict}
    for result in results:
        counts[result.verdict] += 1

    print(
        "  "
        f"{_c('[OK]', 'green')} {counts[PortVerdict.PASS]}  "
        f"{_c('[WARN]', 'yellow')} {counts[PortVerdict.WARN]}  "
        f"{_c('[FAIL]', 'red')} {counts[PortVerdict.FAIL]}  "
        f"{_c('[SKIP]', 'dim')} {counts[PortVerdict.SKIP]}"
    )
    print()
    for result in results:
        print(_format_port_result(result))
        for note in result.notes[:3]:
            print(f"       - {note}")


def _format_port_result(result: PortTestResult) -> str:
    label = _verdict_label(result.verdict)
    return f"  {label} Порт {result.port.name} ({result.port.type.value})"


def _verdict_label(verdict: PortVerdict) -> str:
    if verdict == PortVerdict.PASS:
        return _c("[OK]", "green")
    if verdict == PortVerdict.WARN:
        return _c("[WARN]", "yellow")
    if verdict == PortVerdict.FAIL:
        return _c("[FAIL]", "red")
    return _c("[SKIP]", "dim")


def _state_prefix(state: WalkTestState) -> str:
    mapping = {
        WalkTestState.BASELINE: _c("[...]", "cyan"),
        WalkTestState.WAIT_LINK: _c("[WAIT]", "cyan"),
        WalkTestState.DETECT_PORT: _c("[DETECT]", "cyan"),
        WalkTestState.TEST_LINK: _c("[LINK]", "cyan"),
        WalkTestState.TEST_POE: _c("[PoE]", "cyan"),
        WalkTestState.TEST_SFP: _c("[SFP]", "cyan"),
        WalkTestState.TEST_TRAFFIC: _c("[IPERF]", "cyan"),
        WalkTestState.SHUTDOWN: _c("[OFF]", "yellow"),
        WalkTestState.DONE: _c("[OK]", "green"),
    }
    return mapping.get(state, _c("[...]", "cyan"))


def _progress_bar(done: int, total: int, width: int = 18) -> str:
    if total <= 0:
        return "[" + "-" * width + "]"
    done = min(done, total)
    filled = round(width * done / total)
    return "[" + "#" * filled + "-" * (width - filled) + f"] {done}/{total}"


def _section(title: str) -> None:
    print()
    print(_c(f"== {title} ==", "bold"))


def _confirm(prompt: str, default: bool = True) -> bool:
    suffix = " [Y/n] " if default else " [y/N] "
    answer = input(prompt + suffix).strip().lower()
    if not answer:
        return default
    return answer in ("y", "yes", "д", "да")


if __name__ == "__main__":
    show_start_menu()
    sys.exit(0)
