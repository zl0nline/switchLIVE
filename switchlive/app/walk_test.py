"""Walk-test state machine (#8).

Обходит порты по одному:
1. Ждёт подключения кабеля оператором.
2. Определяет активный порт (#9).
3. Тестирует линк: speed, duplex, counters.
4. Дополнительные тесты (PoE, SFP, iperf — через test steps).
5. Записывает результат.
6. Shutdown порта — сигнал оператору.
7. Повторяет для следующего порта.

State machine не зависит от вендора — все команды через DeviceAdapter.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum

from switchlive.app.port_detection import (
    DetectionResult,
    detect_active_port_with_retry,
    take_mac_baseline,
)
from switchlive.core.models import MacEntry, PortInfo, PortType, PortVerdict
from switchlive.core.timeouts import TimeoutPolicy
from switchlive.devices.base import DeviceAdapter, DeviceSession

log = logging.getLogger(__name__)


def _format_link_status(port: PortInfo) -> str:
    speed = f"{port.actual_speed}M" if port.actual_speed else "unknown"
    duplex = port.duplex or "unknown"
    return f"Link: {port.link_status.value}, speed: {speed}, duplex: {duplex}"


def _format_counters(counters: dict[str, int]) -> str:
    if not counters:
        return "Counters: нет данных"
    return "Counters: " + ", ".join(f"{key}={value}" for key, value in sorted(counters.items()))


class WalkTestState(str, Enum):
    """Состояния walk-test."""

    INIT = "init"
    BASELINE = "baseline"
    WAIT_LINK = "wait_link"
    DETECT_PORT = "detect_port"
    TEST_LINK = "test_link"
    TEST_TRAFFIC = "test_traffic"
    TEST_POE = "test_poe"
    TEST_SFP = "test_sfp"
    SHUTDOWN = "shutdown"
    NEXT_PORT = "next_port"
    DONE = "done"


@dataclass
class PortTestResult:
    """Результат тестирования одного порта."""

    port: PortInfo
    verdict: PortVerdict = PortVerdict.SKIP
    notes: list[str] = field(default_factory=list)
    detection: DetectionResult | None = None
    counters: dict[str, int] = field(default_factory=dict)
    iperf_throughput: float = 0.0
    traffic_passed: bool = False
    sfp: object | None = None


@dataclass
class WalkTestConfig:
    """Конфигурация walk-test."""

    # Какие порты пропускать
    skip_management: bool = True
    skip_console: bool = True
    skip_port_indexes: set[int] = field(default_factory=set)

    # Таймауты
    timeout_policy: TimeoutPolicy = field(default_factory=TimeoutPolicy)

    # Port detection
    detection_retries: int = 3
    detection_delay: float = 2.0

    # Traffic test
    run_traffic: bool = False  # iperf
    iperf_config: object | None = None  # IperfConfig, избегаем circular import

    # PoE
    run_poe: bool = True
    poe_camera_ip: str = ""  # IP PoE-камеры для проверки

    # SFP
    run_sfp: bool = True


class WalkTestEngine:
    """Движок walk-test: пошаговый обход портов.

    Не зависит от вендора. Все vendor-специфичные команды — через adapter.
    """

    def __init__(
        self,
        adapter: DeviceAdapter,
        session: DeviceSession,
        config: WalkTestConfig | None = None,
    ) -> None:
        self.adapter = adapter
        self.session = session
        self.config = config or WalkTestConfig()
        self.state: WalkTestState = WalkTestState.INIT
        self.results: list[PortTestResult] = []
        self.shutdown_ports: set[int] = set()
        self._baseline: dict[str, MacEntry] | None = None  # sentinel: None = not taken yet
        self._should_stop = None  # callback: () -> bool, set externally

    def set_stop_callback(self, callback) -> None:
        """Set a callback that returns True when the test should stop."""
        self._should_stop = callback

    def run(
        self,
        ports: list[PortInfo] | None = None,
        progress_callback=None,
        continue_callback=None,
    ) -> list[PortTestResult]:
        """Запустить walk-test по всем портам.

        Args:
            ports: список портов (если None — берёт из adapter).
            progress_callback: функция(state, message) для UI.
            continue_callback: функция(port, number, total) -> bool перед каждым портом.

        Returns:
            Список результатов по каждому порту.
        """
        def _progress(state: WalkTestState, msg: str) -> None:
            log.info("[%s] %s", state.value, msg)
            if progress_callback:
                progress_callback(state, msg)

        if ports is None:
            ports = self.adapter.list_ports(self.session)

        # Фильтруем порты
        testable = self._filter_ports(ports)
        _progress(WalkTestState.INIT, f"Портов к тестированию: {len(testable)}")

        self.results = []

        for i, port in enumerate(testable):
            if continue_callback and not continue_callback(port, i + 1, len(testable)):
                _progress(WalkTestState.DONE, f"Тестирование остановлено: {len(self.results)}/{len(testable)} портов")
                break

            _progress(
                WalkTestState.NEXT_PORT,
                f"Порт {i+1}/{len(testable)}: {port.name} ({port.type.value})",
            )

            result = self._test_port(port, _progress)
            self.results.append(result)

        self.state = WalkTestState.DONE
        _progress(WalkTestState.DONE, f"Тестирование завершено: {len(self.results)} портов")

        return self.results

    def _filter_ports(self, ports: list[PortInfo]) -> list[PortInfo]:
        """Отфильтровать порты, которые не нужно тестировать."""
        filtered = []
        for p in ports:
            if self.config.skip_management and p.type == PortType.MANAGEMENT:
                continue
            if self.config.skip_console and p.type == PortType.CONSOLE:
                continue
            if p.index in self.config.skip_port_indexes:
                continue
            filtered.append(p)
        return filtered

    def _test_port(self, port: PortInfo, _progress) -> PortTestResult:
        """Полный цикл тестирования одного порта."""
        result = PortTestResult(port=port)

        # 1. Baseline MAC (обновляем перед каждым портом — uplink MAC
        # мог появиться или исчезнуть с предыдущего теста)
        self.state = WalkTestState.BASELINE
        self._baseline = take_mac_baseline(self.adapter, self.session)
        _progress(WalkTestState.BASELINE, f"Baseline MAC: {len(self._baseline)} записей")

        self._enable_port(port, _progress)

        # 2. Ждать подключения (link up)
        self.state = WalkTestState.WAIT_LINK
        _progress(WalkTestState.WAIT_LINK, f"Подключите кабель в порт {port.name}")

        # 3. Определить активный порт
        self.state = WalkTestState.DETECT_PORT
        detection = detect_active_port_with_retry(
            self.adapter,
            self.session,
            self._baseline,
            [port],  # только этот порт
            self.shutdown_ports,
            self.config.detection_retries,
            self.config.detection_delay,
            should_stop=self._should_stop,
        )
        result.detection = detection

        if detection.port is None:
            result.verdict = PortVerdict.WARN
            result.notes.extend(detection.warnings)
            _progress(
                WalkTestState.DETECT_PORT,
                f"⚠️ Порт не определён: {detection.warnings}",
            )
            return result

        # Обновляем baseline — добавляем найденный MAC
        _progress(
            WalkTestState.DETECT_PORT,
            f"Порт определён: {detection.port.name} ({detection.method})",
        )

        # 4. Тест линка: counters
        self.state = WalkTestState.TEST_LINK
        try:
            self._refresh_port_state(port)
            _progress(WalkTestState.TEST_LINK, _format_link_status(port))

            counters = self.adapter.get_counters(self.session, port)
            result.counters = counters
            _progress(WalkTestState.TEST_LINK, _format_counters(counters))

            # Оценка counters
            crc = counters.get("crc", 0)
            drops = counters.get("drops", 0)
            if crc > 0 or drops > 0:
                result.verdict = PortVerdict.WARN
                result.notes.append(f"CRC={crc}, drops={drops}")
            else:
                result.verdict = PortVerdict.PASS
                if not counters:
                    result.notes.append("Counters unavailable")
        except Exception as e:
            result.verdict = PortVerdict.WARN
            result.notes.append(f"Counters error: {e}")

        # 5. PoE тест (через нормализованный probe)
        if self.config.run_poe and port.supports_poe:
            self.state = WalkTestState.TEST_POE
            try:
                from switchlive.app.poe import (
                    PoEVerdict,
                    evaluate_poe_verdict,
                    probe_poe_status,
                    wait_for_camera,
                )

                poe = probe_poe_status(self.adapter, self.session, port)
                _progress(
                    WalkTestState.TEST_POE,
                    f"PoE state: {poe.state.value}, "
                    f"power: {poe.power_w}W, class: {poe.poe_class}",
                )

                # Если питание есть и задан IP камеры — ждём загрузки
                camera_reachable = None
                if poe.powered and self.config.poe_camera_ip:
                    reachable, waited = wait_for_camera(
                        self.config.poe_camera_ip,
                        timeout=self.config.timeout_policy.poe,
                        progress_callback=lambda m: _progress(
                            WalkTestState.TEST_POE, m
                        ),
                    )
                    poe.camera_ip = self.config.poe_camera_ip
                    poe.camera_reachable = reachable
                    poe.boot_time_sec = waited
                    camera_reachable = reachable

                # Оценка независимого PoE-вердикта
                poe = evaluate_poe_verdict(
                    poe,
                    camera_reachable=camera_reachable,
                )

                result.notes.append(
                    f"PoE: {poe.verdict.value} "
                    f"({poe.state.value}, {poe.power_w}W)"
                )

                # PoE WARN/FAIL не обязательно понижает общий вердикт —
                # это отдельная оценка, но фиксируем
                if poe.verdict in (PoEVerdict.FAIL, PoEVerdict.WARN):
                    if result.verdict == PortVerdict.PASS:
                        result.verdict = PortVerdict.WARN
                    result.notes.append(f"PoE detail: {'; '.join(poe.notes)}")

            except Exception as e:
                result.notes.append(f"PoE check failed: {e}")

        # 6. Traffic test (iperf) — если включён
        if self.config.run_traffic:
            self.state = WalkTestState.TEST_TRAFFIC
            try:
                from switchlive.app.traffic_iperf import (
                    IperfConfig,
                    run_iperf_test,
                )

                iperf_cfg = self.config.iperf_config
                if not isinstance(iperf_cfg, IperfConfig):
                    iperf_cfg = IperfConfig()

                _progress(
                    WalkTestState.TEST_TRAFFIC,
                    f"iperf3 TCP unlimited → {iperf_cfg.server_host}:{iperf_cfg.server_port} "
                    f"streams={iperf_cfg.parallel_streams}",
                )
                iperf_result = run_iperf_test(iperf_cfg)

                result.iperf_throughput = iperf_result.throughput_mbps

                if iperf_result.verdict == "FAIL":
                    result.notes.append(
                        f"iperf FAIL: {iperf_result.error}"
                    )
                    if result.verdict == PortVerdict.PASS:
                        result.verdict = PortVerdict.WARN
                elif iperf_result.verdict == "WARN":
                    result.notes.append(
                        f"iperf WARN: {iperf_result.throughput_mbps} Mbps, "
                        f"loss {iperf_result.loss_percent}%"
                    )
                    if result.verdict == PortVerdict.PASS:
                        result.verdict = PortVerdict.WARN
                else:
                    result.traffic_passed = True
                    result.notes.append(
                        f"iperf PASS: {iperf_result.throughput_mbps} Mbps"
                    )
                    if _looks_like_100m_path_bottleneck(port, iperf_result.throughput_mbps):
                        result.notes.append(
                            "Подсказка iperf: порт поднят в 1G+, но скорость около 100M; "
                            "проверьте uplink, серверный порт, кабель или адаптер"
                        )
                        if result.verdict == PortVerdict.PASS:
                            result.verdict = PortVerdict.WARN

                _progress(
                    WalkTestState.TEST_TRAFFIC,
                    f"iperf: {iperf_result.throughput_mbps} Mbps "
                    f"({iperf_result.verdict})",
                )
            except Exception as e:
                result.notes.append(f"iperf error: {e}")
                _progress(
                    WalkTestState.TEST_TRAFFIC,
                    f"⚠️ iperf не выполнен: {e}",
                )

        # 7. SFP тест (если SFP/SFP+ порт)
        if self.config.run_sfp and port.type in (PortType.SFP, PortType.SFP_PLUS, PortType.COMBO):
            self.state = WalkTestState.TEST_SFP
            try:
                from switchlive.app.sfp import SfpVerdict, probe_sfp_status

                sfp = probe_sfp_status(self.adapter, self.session, port)
                result.sfp = sfp
                result.notes.append(
                    f"SFP: {sfp.verdict.value} "
                    f"(vendor={sfp.vendor or 'unknown'}, "
                    f"serial={sfp.serial or 'unknown'}, "
                    f"rx={sfp.rx_power_dbm}, tx={sfp.tx_power_dbm}, "
                    f"temp={sfp.temperature_c})"
                )
                _progress(
                    WalkTestState.TEST_SFP,
                    f"SFP: {sfp.verdict.value}, "
                    f"vendor={sfp.vendor or 'unknown'}, "
                    f"serial={sfp.serial or 'unknown'}",
                )

                if sfp.verdict in (SfpVerdict.FAIL, SfpVerdict.WARN):
                    if result.verdict == PortVerdict.PASS:
                        result.verdict = PortVerdict.WARN
                    if sfp.notes:
                        result.notes.append(f"SFP detail: {'; '.join(sfp.notes)}")
            except Exception as e:
                result.notes.append(f"SFP check failed: {e}")

        # 8. Shutdown порта только после успешного теста
        if self._should_shutdown_after_test(result):
            self._shutdown_port(port, _progress)
        else:
            _progress(
                WalkTestState.SHUTDOWN,
                f"Порт {port.name} оставлен включённым для повторной проверки",
            )

        return result

    def _enable_port(self, port: PortInfo, _progress) -> None:
        try:
            self.adapter.no_shutdown_port(self.session, port)
        except Exception as e:
            _progress(
                WalkTestState.WAIT_LINK,
                f"⚠️ Не удалось включить порт {port.name}: {e}",
            )

    def _refresh_port_state(self, port: PortInfo) -> None:
        ports = self.adapter.list_ports(self.session)
        live = next((item for item in ports if item.index == port.index), None)
        if not live:
            return
        port.admin_status = live.admin_status
        port.link_status = live.link_status
        port.actual_speed = live.actual_speed
        port.duplex = live.duplex

    def _should_shutdown_after_test(self, result: PortTestResult) -> bool:
        if self.config.run_traffic:
            return result.traffic_passed
        return result.verdict == PortVerdict.PASS

    def _shutdown_port(self, port: PortInfo, _progress) -> None:
        """Shutdown порта — сигнал оператору для перестановки кабеля."""
        self.state = WalkTestState.SHUTDOWN
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                self.adapter.shutdown_port(self.session, port)
                # Verify shutdown by checking port state
                if self._verify_port_shutdown(port):
                    self.shutdown_ports.add(port.index)
                    _progress(
                        WalkTestState.SHUTDOWN,
                        f"Порт {port.name} выключен — можно переставлять кабель",
                    )
                    return
                _progress(
                    WalkTestState.SHUTDOWN,
                    f"Попытка {attempt + 1}/{max_attempts}: порт {port.name} всё ещё активен, retry...",
                )
            except Exception as e:
                _progress(
                    WalkTestState.SHUTDOWN,
                    f"⚠️ Shutdown порт {port.name} (попытка {attempt + 1}): {e}",
                )

        _progress(
            WalkTestState.SHUTDOWN,
            f"⚠️ Не удалось shutdown порт {port.name} после {max_attempts} попыток",
        )

    def _verify_port_shutdown(self, port: PortInfo) -> bool:
        """Verify port is actually disabled by checking link status."""
        try:
            live_ports = self.adapter.list_ports(self.session)
            live = next((p for p in live_ports if p.index == port.index), None)
            if live is None:
                return True  # port not found, assume shutdown
            from switchlive.core.models import LinkStatus, AdminStatus
            return live.admin_status == AdminStatus.DISABLED or live.link_status == LinkStatus.DOWN
        except Exception:
            return True  # can't verify, assume success


def _looks_like_100m_path_bottleneck(port: PortInfo, throughput_mbps: float) -> bool:
    return port.actual_speed >= 1000 and 80 <= throughput_mbps <= 120
