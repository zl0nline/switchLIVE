"""Определение активного порта (#9).

Логика:
1. Снять baseline MAC-таблицу до подключения тестового кабеля.
2. Оператор подключает кабель.
3. Тестовый хост генерирует трафик (пара ARP/ping).
4. Снять MAC-таблицу снова.
5. Delta = новые MAC-адреса, которых не было в baseline.
6. Delta → port_index = активный порт.

Дополнительные сигналы:
- link status changes (порт был down → стал up)
- counters delta (rx_packets выросли)

Важно: ранее протестированные порты уже в shutdown — они не мешают.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from switchlive.core.models import MacEntry, PortInfo
from switchlive.devices.base import DeviceAdapter, DeviceSession

log = logging.getLogger(__name__)


@dataclass
class DetectionResult:
    """Результат определения активного порта."""

    port: PortInfo | None = None
    method: str = ""  # "mac_delta", "link_status", "manual"
    confidence: str = ""  # "high", "medium", "low"
    warnings: list[str] = None

    def __post_init__(self) -> None:
        if self.warnings is None:
            self.warnings = []


def take_mac_baseline(
    adapter: DeviceAdapter, session: DeviceSession
) -> dict[str, MacEntry]:
    """Снять baseline MAC-таблицу.

    Возвращает dict: {mac_address: MacEntry}.
    """
    entries = adapter.get_mac_table(session)
    return {e.mac: e for e in entries}


def detect_active_port(
    adapter: DeviceAdapter,
    session: DeviceSession,
    baseline: dict[str, MacEntry],
    ports: list[PortInfo],
    shutdown_ports: set[int] | None = None,
) -> DetectionResult:
    """Определить активный порт через MAC delta.

    Args:
        adapter: адаптер устройства.
        session: активная сессия.
        baseline: MAC-таблица до подключения (из take_mac_baseline).
        ports: список всех портов устройства.
        shutdown_ports: индексы уже протестированных (shutdown) портов.

    Returns:
        DetectionResult с найденным портом или предупреждениями.
    """
    if shutdown_ports is None:
        shutdown_ports = set()

    port_by_index = {p.index: p for p in ports}

    # Снять текущую MAC-таблицу
    current_entries = adapter.get_mac_table(session)

    # Delta: MAC-адреса, которых не было в baseline
    new_macs: list[MacEntry] = []
    for entry in current_entries:
        if entry.mac not in baseline:
            new_macs.append(entry)

    if not new_macs:
        log.warning("No new MAC addresses detected after cable connection")
        return DetectionResult(
            port=None,
            method="mac_delta",
            confidence="low",
            warnings=[
                "Нет новых MAC в таблице — возможно кабель не подключён",
                "или трафик от тестового хоста не дошёл",
            ],
        )

    # Группируем new MACs по портам
    ports_with_new_macs: dict[int, list[str]] = {}
    for entry in new_macs:
        # Пропускаем shutdown порты
        if entry.port_index in shutdown_ports:
            continue
        ports_with_new_macs.setdefault(entry.port_index, []).append(entry.mac)

    # Фильтруем известные порты
    valid_ports = {
        idx: macs
        for idx, macs in ports_with_new_macs.items()
        if idx in port_by_index
    }

    if not valid_ports:
        return DetectionResult(
            port=None,
            method="mac_delta",
            confidence="low",
            warnings=[
                f"Новые MAC на неизвестных портах: {list(ports_with_new_macs.keys())}",
            ],
        )

    if len(valid_ports) > 1:
        # Несколько активных портов — неоднозначно
        port_list = list(valid_ports.keys())
        return DetectionResult(
            port=None,
            method="mac_delta",
            confidence="low",
            warnings=[
                f"Несколько портов с новыми MAC: {port_list}",
                "Изолируйте тестовый кабель — отключите лишние",
            ],
        )

    # Один порт — нашли!
    port_idx = next(iter(valid_ports))
    port = port_by_index[port_idx]
    macs = valid_ports[port_idx]

    log.info(
        "Active port detected: index=%s name=%s macs=%s",
        port.index,
        port.cli_name,
        macs,
    )

    return DetectionResult(
        port=port,
        method="mac_delta",
        confidence="high",
    )


def detect_existing_uplink_by_mac_count(
    adapter: DeviceAdapter,
    session: DeviceSession,
    ports: list[PortInfo],
    shutdown_ports: set[int] | None = None,
) -> DetectionResult:
    """Detect already-connected uplink by existing MAC concentration.

    Uplink is often connected before baseline, so MAC delta is empty. For uplink
    preflight, existing learned MACs are signal, not noise.
    """
    if shutdown_ports is None:
        shutdown_ports = set()

    port_by_index = {port.index: port for port in ports}
    counts: dict[int, int] = {}
    for entry in adapter.get_mac_table(session):
        if entry.port_index in shutdown_ports or entry.port_index not in port_by_index:
            continue
        counts[entry.port_index] = counts.get(entry.port_index, 0) + 1

    if not counts:
        return DetectionResult(
            port=None,
            method="existing_mac_count",
            confidence="low",
            warnings=["Нет существующих MAC на uplink-кандидатах"],
        )

    port_idx, mac_count = max(counts.items(), key=lambda item: item[1])
    port = port_by_index[port_idx]
    confidence = "high" if mac_count >= 2 else "medium"
    log.info(
        "Existing uplink detected: index=%s name=%s mac_count=%s",
        port.index,
        port.cli_name,
        mac_count,
    )
    return DetectionResult(
        port=port,
        method="existing_mac_count",
        confidence=confidence,
    )


def detect_active_port_with_retry(
    adapter: DeviceAdapter,
    session: DeviceSession,
    baseline: dict[str, MacEntry],
    ports: list[PortInfo],
    shutdown_ports: set[int] | None = None,
    max_retries: int = 3,
    retry_delay: float = 2.0,
) -> DetectionResult:
    """Повторять определение порта с задержкой.

    Тестовый хост может не сразу отправить трафик.
    """
    import time

    for attempt in range(max_retries):
        result = detect_active_port(
            adapter, session, baseline, ports, shutdown_ports
        )
        if result.port is not None:
            return result

        if attempt < max_retries - 1:
            log.info(
                "Retry %d/%d: waiting %.1fs...",
                attempt + 1,
                max_retries,
                retry_delay,
            )
            time.sleep(retry_delay)

    return result
