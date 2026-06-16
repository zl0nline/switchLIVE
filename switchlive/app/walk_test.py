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
from switchlive.core.models import PortInfo, PortType, PortVerdict
from switchlive.core.timeouts import TimeoutPolicy
from switchlive.devices.base import DeviceAdapter, DeviceSession

log = logging.getLogger(__name__)


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


@dataclass
class WalkTestConfig:
    """Конфигурация walk-test."""

    # Какие порты пропускать
    skip_management: bool = True
    skip_console: bool = True

    # Таймауты
    timeout_policy: TimeoutPolicy = field(default_factory=TimeoutPolicy)

    # Port detection
    detection_retries: int = 3
    detection_delay: float = 2.0

    # Traffic test
    run_traffic: bool = False  # iperf — #10, пока заглушка

    # PoE
    run_poe: bool = True

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
        self._baseline: dict = {}

    def run(
        self,
        ports: list[PortInfo] | None = None,
        progress_callback=None,
    ) -> list[PortTestResult]:
        """Запустить walk-test по всем портам.

        Args:
            ports: список портов (если None — берёт из adapter).
            progress_callback: функция(state, message) для UI.

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

        results = []

        for i, port in enumerate(testable):
            _progress(
                WalkTestState.NEXT_PORT,
                f"Порт {i+1}/{len(testable)}: {port.name} ({port.type.value})",
            )

            result = self._test_port(port, _progress)
            results.append(result)

        self.state = WalkTestState.DONE
        _progress(WalkTestState.DONE, f"Тестирование завершено: {len(results)} портов")

        self.results = results
        return results

    def _filter_ports(self, ports: list[PortInfo]) -> list[PortInfo]:
        """Отфильтровать порты, которые не нужно тестировать."""
        filtered = []
        for p in ports:
            if self.config.skip_management and p.type == PortType.MANAGEMENT:
                continue
            if self.config.skip_console and p.type == PortType.CONSOLE:
                continue
            filtered.append(p)
        return filtered

    def _test_port(self, port: PortInfo, _progress) -> PortTestResult:
        """Полный цикл тестирования одного порта."""
        result = PortTestResult(port=port)

        # 1. Baseline MAC (первый раз)
        if not self._baseline:
            self.state = WalkTestState.BASELINE
            self._baseline = take_mac_baseline(self.adapter, self.session)
            _progress(WalkTestState.BASELINE, f"Baseline MAC: {len(self._baseline)} записей")

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
        )
        result.detection = detection

        if detection.port is None:
            result.verdict = PortVerdict.WARN
            result.notes.extend(detection.warnings)
            _progress(
                WalkTestState.DETECT_PORT,
                f"⚠️ Порт не определён: {detection.warnings}",
            )
            # Всё равно shutdown
            self._shutdown_port(port, _progress)
            return result

        # Обновляем baseline — добавляем найденный MAC
        _progress(
            WalkTestState.DETECT_PORT,
            f"Порт определён: {detection.port.name} ({detection.method})",
        )

        # 4. Тест линка: counters
        self.state = WalkTestState.TEST_LINK
        try:
            counters = self.adapter.get_counters(self.session, port)
            result.counters = counters
            _progress(
                WalkTestState.TEST_LINK,
                f"Counters: {counters}",
            )

            # Оценка counters
            crc = counters.get("crc", 0)
            drops = counters.get("drops", 0)
            if crc > 0 or drops > 0:
                result.verdict = PortVerdict.WARN
                result.notes.append(f"CRC={crc}, drops={drops}")
            else:
                result.verdict = PortVerdict.PASS
        except Exception as e:
            result.verdict = PortVerdict.WARN
            result.notes.append(f"Counters error: {e}")

        # 5. PoE тест (если поддерживается)
        if self.config.run_poe and port.supports_poe:
            self.state = WalkTestState.TEST_POE
            try:
                # Адаптер может вернуть PoE статус
                if hasattr(self.adapter, "get_poe_status"):
                    poe = self.adapter.get_poe_status(self.session, port)
                    if poe:
                        result.notes.append(f"PoE: {poe}")
                        _progress(WalkTestState.TEST_POE, f"PoE: {poe}")
            except Exception as e:
                result.notes.append(f"PoE check failed: {e}")

        # 6. SFP тест (если SFP/SFP+ порт)
        if self.config.run_sfp and port.type in (PortType.SFP, PortType.SFP_PLUS, PortType.COMBO):
            self.state = WalkTestState.TEST_SFP
            try:
                if hasattr(self.adapter, "get_transceiver"):
                    sfp = self.adapter.get_transceiver(self.session, port)
                    if sfp:
                        result.notes.append(f"SFP: {sfp}")
                        _progress(WalkTestState.TEST_SFP, f"SFP: {sfp}")
            except Exception as e:
                result.notes.append(f"SFP check failed: {e}")

        # 7. Shutdown порта
        self._shutdown_port(port, _progress)

        return result

    def _shutdown_port(self, port: PortInfo, _progress) -> None:
        """Shutdown порта — сигнал оператору для перестановки кабеля."""
        self.state = WalkTestState.SHUTDOWN
        try:
            self.adapter.shutdown_port(self.session, port)
            self.shutdown_ports.add(port.index)
            _progress(
                WalkTestState.SHUTDOWN,
                f"Порт {port.name} выключен — можно переставлять кабель",
            )
        except Exception as e:
            _progress(
                WalkTestState.SHUTDOWN,
                f"⚠️ Не удалось shutdown порт {port.name}: {e}",
            )
