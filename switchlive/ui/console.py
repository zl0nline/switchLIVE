"""Консольный UI для оператора."""

from __future__ import annotations

import re
import select
import sys
import time
from datetime import datetime

from switchlive.app.console_probe import baudrates_from_config
from switchlive.app.discovery import run_discovery
from switchlive.app.finalize import FinalizeConfig, finalize_after_test
from switchlive.app.port_detection import (
    detect_active_port,
    detect_existing_uplink_by_mac_count,
    take_mac_baseline,
)
from switchlive.app.test_result_builder import build_test_result
from switchlive.app.traffic_iperf import (
    IperfConfig,
    check_iperf3_available,
)
from switchlive.app.walk_test import (
    PortTestResult,
    WalkTestConfig,
    WalkTestEngine,
    WalkTestState,
)
from switchlive.config import Config
from switchlive.core.credentials import Credentials
from switchlive.core.models import LinkStatus, PortInfo, PortType, PortVerdict
from switchlive.core.timeouts import TimeoutPolicy
from switchlive.diagnostics import DebugContext, collect_debug_bundle, configure_logging
from switchlive.storage.history import list_recent_runs

ANSI = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "dim": "\033[2m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "red": "\033[31m",
    "cyan": "\033[36m",
}

FINISH_COMMANDS = {"q", "quit", "stop", "finish", "end", "й", "стоп", "завершить", "0"}


class _OperatorStopRequested(Exception):
    """Raised when operator asks to finish and save partial results."""


class _FinishKeyWatcher:
    """Non-blocking terminal watcher for single-key `q` press.

    On the first call, switches stdin to cbreak mode so that keys are
    available immediately without Enter. Restores the original terminal
    settings on close/finish.
    """

    def __init__(self, stream=None) -> None:
        self.stream = stream or sys.stdin
        self._requested = False
        self._armed = False
        self._old_settings: list | None = None

    def _arm(self) -> None:
        """Switch terminal to cbreak mode for single-key reads."""
        if self._armed:
            return
        try:
            import termios
            import tty
            self._old_settings = termios.tcgetattr(self.stream.fileno())
            tty.setcbreak(self.stream.fileno())
            self._armed = True
        except (ImportError, OSError, ValueError):
            # Not a real terminal (e.g. piped stdin) — fall back to line mode
            pass

    def _disarm(self) -> None:
        """Restore original terminal settings."""
        if not self._armed or self._old_settings is None:
            return
        try:
            import termios
            termios.tcsetattr(self.stream.fileno(), termios.TCSADRAIN, self._old_settings)
        except (OSError, ValueError, ImportError):
            pass
        self._armed = False
        self._old_settings = None

    def requested(self) -> bool:
        if self._requested:
            return True
        self._arm()
        try:
            ready, _, _ = select.select([self.stream], [], [], 0)
        except (OSError, ValueError):
            return False
        if not ready:
            return False

        if self._armed:
            # cbreak mode: read single char
            ch = self.stream.read(1).lower()
            self._requested = ch in ("q", "й")
        else:
            # Fallback: line mode
            line = self.stream.readline().strip().lower()
            self._requested = line in FINISH_COMMANDS
        return self._requested

    def close(self) -> None:
        self._disarm()


def _c(text: str, color: str) -> str:
    return f"{ANSI.get(color, '')}{text}{ANSI['reset']}"


def _print_menu() -> None:
    print()
    print("=" * 50)
    print("  switchLIVE — тестирование коммутаторов")
    print("=" * 50)
    print()
    print("  1. 🔍 Определение коммутатора")
    print("  2. ▶️  Тест портов / traffic")
    print("  3. ⚡ PoE тест")
    print("  4. 📋 История тестов")
    print("  5. ⚙️  Настройки")
    print("  6. 🧰 Собрать debug bundle")
    print("  0. 🚪 Выход")
    print()


def _print_bottom_menu() -> None:
    print()
    print("-" * 50)
    print("  Команды: 1 определить | 2 порты | 3 PoE | 4 история | 5 настройки | 6 debug | 0 выход")
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
            baudrates=baudrates_from_config(config),
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

        try:
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
                _handle_poe_test_menu(config)
                _print_bottom_menu()
            elif choice == "4":
                _handle_history_menu(config)
                _print_bottom_menu()
            elif choice == "5":
                print("\n  ⚠️ Настройки — ещё не реализовано\n")
                _print_bottom_menu()
            elif choice == "6":
                _handle_debug_bundle(config, config_path, debug_context)
                _print_bottom_menu()
            else:
                print("\n  ❌ Неизвестная команда\n")
                _print_bottom_menu()
        except KeyboardInterrupt:
            print()
            print(_c("  Операция прервана оператором. Выход.", "yellow"))
            break


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

    uplink_ready, uplink = _prepare_uplink(adapter, session, ports, config)
    if not uplink_ready:
        return

    skip_indexes = set()
    if uplink:
        skip_indexes.add(uplink.index)

    test_config = _configure_walk_test(config, skip_port_indexes=skip_indexes)
    engine = WalkTestEngine(adapter, session, test_config)

    _section("Ход тестирования")
    print(_c("  Тест идёт автоматически. Нажмите q, чтобы закончить и сохранить отчёт.", "cyan"))
    progress_total = len(engine._filter_ports(ports))
    started_at = datetime.now()
    watcher = _FinishKeyWatcher()
    engine.set_stop_callback(watcher.requested)
    try:
        results = engine.run(
            ports=ports,
            progress_callback=_make_stoppable_walk_progress(progress_total, watcher),
            continue_callback=lambda port, number, total: not watcher.requested(),
        )
    except (KeyboardInterrupt, _OperatorStopRequested):
        print()
        print(_c("  [STOP] Тест остановлен оператором. Сохраняю частичный отчёт.", "yellow"))
        results = engine.results
    finally:
        watcher.close()

    _print_walk_summary(results)
    _persist_test_artifacts(
        adapter=adapter,
        session=session,
        identity=discovery.identity,
        results=results,
        started_at=started_at,
        config=config,
        comments="traffic walk-test",
    )


def _handle_poe_test_menu(config: Config) -> None:
    """Separate PoE-only wizard."""
    _section("PoE тестирование")
    discovery = _run_discovery_wizard(config)
    if not discovery.found or not discovery.adapter or not discovery.session:
        print(_c("  [FAIL] Сначала не удалось определить устройство", "red"))
        return

    _print_device_summary(discovery)
    adapter = discovery.adapter
    session = discovery.session
    poe_ports = [port for port in adapter.list_ports(session) if port.supports_poe]
    if not poe_ports:
        print(_c("  [SKIP] В профиле устройства нет PoE-портов", "yellow"))
        return

    print()
    print(f"  PoE-портов к проверке: {len(poe_ports)}")
    if not _confirm("  Запустить PoE тест?", default=True):
        print("  PoE тест отменён оператором.")
        return

    test_config = _configure_poe_test(config)
    engine = WalkTestEngine(adapter, session, test_config)
    _section("Ход PoE тестирования")
    print(_c("  Тест идёт автоматически. Нажмите q, чтобы закончить и сохранить отчёт.", "cyan"))
    started_at = datetime.now()
    watcher = _FinishKeyWatcher()
    engine.set_stop_callback(watcher.requested)
    try:
        results = engine.run(
            ports=poe_ports,
            progress_callback=_make_stoppable_walk_progress(len(poe_ports), watcher),
            continue_callback=lambda port, number, total: not watcher.requested(),
        )
    except (KeyboardInterrupt, _OperatorStopRequested):
        print()
        print(_c("  [STOP] Тест остановлен оператором. Сохраняю частичный отчёт.", "yellow"))
        results = engine.results
    finally:
        watcher.close()
    _print_walk_summary(results)
    _persist_test_artifacts(
        adapter=adapter,
        session=session,
        identity=discovery.identity,
        results=results,
        started_at=started_at,
        config=config,
        comments="poe test",
    )


def _handle_history_menu(config: Config) -> None:
    """Show recent saved test runs."""
    _section("История тестов")
    rows = list_recent_runs(config.db_path, limit=20)
    if not rows:
        print(_c("  История пока пустая.", "yellow"))
        return

    for row in rows:
        finished = row.get("finished_at") or ""
        print(
            "  "
            f"#{row['id']} {finished[:19]} "
            f"{row['vendor']} {row['model']} "
            f"serial={row['serial']} "
            f"ports={row.get('port_count', 0)} "
            f"overall={row['overall_verdict']}"
        )


def _persist_test_artifacts(
    *,
    adapter,
    session,
    identity,
    results: list[PortTestResult],
    started_at: datetime,
    config: Config,
    comments: str,
) -> None:
    """Save history and reports for full or partial test runs."""
    test_result = build_test_result(
        identity,
        results,
        started_at=started_at,
        finished_at=datetime.now(),
        comments=comments,
    )
    finalize = finalize_after_test(
        adapter,
        session,
        test_result,
        FinalizeConfig(
            factory_reset=False,
            report_dir=config.report_dir,
            db_path=config.db_path,
        ),
    )
    if finalize.errors:
        print(_c(f"  [WARN] Отчёт/история не сохранены: {'; '.join(finalize.errors)}", "yellow"))
        return

    print(_c("  [OK] Результаты сохранены", "green"))
    if finalize.history_run_id is not None:
        print(f"     История: run #{finalize.history_run_id}")
    if finalize.html_report:
        print(f"     HTML: {finalize.html_report}")
    if finalize.csv_report:
        print(f"     CSV:  {finalize.csv_report}")


def _configure_walk_test(
    config: Config | None = None,
    skip_port_indexes: set[int] | None = None,
) -> WalkTestConfig:
    """Collect walk-test settings from operator."""
    config = config or Config()
    print()
    print(_c("  Настройка traffic test", "bold"))

    iperf_config = None
    run_traffic = False
    if check_iperf3_available():
        server_ip = _input_with_default(
            "  IP iperf-сервера",
            config.iperf_server_host or "",
            empty_hint="пропустить",
        )
        if server_ip:
            run_traffic = True
            iperf_config = IperfConfig(
                server_host=server_ip,
                server_port=config.iperf_server_port,
                duration_sec=config.iperf_duration,
                min_throughput_mbps=config.iperf_min_throughput_mbps,
                max_loss_percent=config.iperf_max_loss_percent,
            )
    else:
        print(_c("  [WARN] iperf3 не найден, трафик-тест будет пропущен.", "yellow"))

    return WalkTestConfig(
        timeout_policy=TimeoutPolicy(
            base=config.link_timeout_sec,
            poe=config.poe_timeout_sec,
            max=config.max_timeout_sec,
        ),
        detection_retries=_detection_retries_for_config(config),
        detection_delay=2.0,
        run_traffic=run_traffic,
        iperf_config=iperf_config,
        run_poe=False,
        skip_port_indexes=skip_port_indexes or set(),
    )


def _configure_poe_test(config: Config | None = None) -> WalkTestConfig:
    """Collect PoE-only settings."""
    config = config or Config()
    print()
    print(_c("  Настройка PoE теста", "bold"))
    poe_camera_ip = input("  IP PoE-камеры (Enter = проверять только питание): ").strip()
    return WalkTestConfig(
        timeout_policy=TimeoutPolicy(
            base=config.link_timeout_sec,
            poe=config.poe_timeout_sec,
            max=config.max_timeout_sec,
        ),
        detection_retries=_detection_retries_for_config(config),
        detection_delay=2.0,
        run_traffic=False,
        run_poe=True,
        poe_camera_ip=poe_camera_ip,
        run_sfp=False,
    )


def _prepare_uplink(adapter, session, ports: list[PortInfo], config: Config) -> tuple[bool, PortInfo | None]:
    """Ensure uplink is visible before asking operator to walk access ports."""
    uplinks = _uplink_candidates(ports)
    if not uplinks:
        uplinks = ports

    candidates = _dedupe_ports([*uplinks, *ports])

    active_link = _active_ports_from_link_status(candidates)
    if active_link:
        print(_c(f"  [OK] Аплинк готов: порт {active_link[0].name}", "green"))
        return True, active_link[0]

    existing_uplink = detect_existing_uplink_by_mac_count(adapter, session, candidates)
    if existing_uplink.port:
        print(_c(f"  [OK] Аплинк готов: порт {existing_uplink.port.name}", "green"))
        return True, existing_uplink.port

    print(_c("  [WAIT] Активный uplink не найден.", "yellow"))
    print("  Подключите uplink. Ожидаю link up или MAC на активном порту...")
    baseline = take_mac_baseline(adapter, session)
    uplink = _wait_for_uplink(adapter, session, baseline, candidates, config)
    if uplink:
        print(_c(f"  [OK] Аплинк готов: порт {uplink.name}", "green"))
        return True, uplink

    print(_c("  [WARN] Аплинк не удалось определить автоматически.", "yellow"))
    if _confirm("  Если uplink физически подключен, продолжить тест?", default=True):
        return True, None
    return False, None


def _uplink_candidates(ports: list[PortInfo]) -> list[PortInfo]:
    return [
        port
        for port in ports
        if port.role in ("uplink", "combo")
        or port.type in (PortType.SFP, PortType.SFP_PLUS, PortType.COMBO)
    ]


def _dedupe_ports(ports: list[PortInfo]) -> list[PortInfo]:
    result = []
    seen = set()
    for port in ports:
        if port.index in seen:
            continue
        result.append(port)
        seen.add(port.index)
    return result


def _active_ports_from_link_status(ports: list[PortInfo]) -> list[PortInfo]:
    return [port for port in ports if port.link_status == LinkStatus.UP]


def _wait_for_uplink(
    adapter,
    session,
    baseline,
    uplinks: list[PortInfo],
    config: Config,
) -> PortInfo | None:
    uplink_indexes = {port.index for port in uplinks}
    for attempt in range(_detection_retries_for_config(config)):
        live_ports = adapter.list_ports(session)
        live_uplinks = [port for port in live_ports if port.index in uplink_indexes]
        active_link = _active_ports_from_link_status(live_uplinks)
        if active_link:
            return active_link[0]

        existing_uplink = detect_existing_uplink_by_mac_count(adapter, session, uplinks)
        if existing_uplink.port:
            return existing_uplink.port

        detection = detect_active_port(
            adapter,
            session,
            baseline,
            uplinks,
            shutdown_ports=set(),
        )
        if detection.port:
            return detection.port

        if attempt < _detection_retries_for_config(config) - 1:
            time.sleep(2.0)
    return None


def _detection_retries_for_config(config: Config) -> int:
    return max(30, int(config.link_timeout_sec / 2))


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


def _make_stoppable_walk_progress(total_ports: int, watcher: _FinishKeyWatcher):
    progress = _make_walk_progress(total_ports)

    def wrapped(state: WalkTestState, msg: str) -> None:
        if watcher.requested():
            raise _OperatorStopRequested
        progress(state, msg)

    return wrapped


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
