"""Нормализованные модели данных.

Используются тестами и отчётами. Не содержат vendor-специфичной логики.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class PortVerdict(str, Enum):
    PASS = "PASS"
    WARN = "PASS_WITH_WARNINGS"
    FAIL = "FAIL"
    SKIP = "SKIP"


class DeviceCategory(str, Enum):
    SWITCH = "switch"
    ROUTER = "router"
    OLT = "olt"
    UPS = "ups"
    PDU = "pdu"
    MEDIA_CONVERTER = "media_converter"
    RADIO = "radio"
    UNKNOWN = "unknown"


@dataclass
class DeviceIdentity:
    vendor: str = "unknown"
    model: str = "unknown"
    serial: str = "unknown"
    firmware: str = "unknown"
    category: DeviceCategory = DeviceCategory.UNKNOWN


@dataclass
class PortInfo:
    """Описание физического порта устройства."""

    index: int
    name: str
    speed_mbps: int = 0
    media: str = ""  # copper, sfp, sfp+, console...
    connector: str = ""  # RJ45, SFP, SFP+, LC...
    supports_poe: bool = False
    role: str = ""  # access, uplink, management...


@dataclass
class PortStatus:
    """Результат тестирования одного порта."""

    port: PortInfo
    link_up: bool = False
    speed_actual: int = 0
    duplex: str = ""
    crc_errors: int = 0
    drops: int = 0
    flaps: int = 0
    mac_learned: list[str] = field(default_factory=list)
    iperf_throughput_mbps: float = 0.0
    poe_status: str = ""
    poe_class: str = ""
    sfp_vendor: str = ""
    sfp_serial: str = ""
    sfp_rx_power: float = 0.0
    sfp_tx_power: float = 0.0
    sfp_temp: float = 0.0
    verdict: PortVerdict = PortVerdict.SKIP
    notes: str = ""


@dataclass
class CommandResult:
    """Результат выполнения CLI-команды."""

    output: str
    success: bool = True
    error: str = ""


@dataclass
class TestResult:
    """Итог тестирования устройства."""

    device: DeviceIdentity
    started_at: datetime = field(default_factory=datetime.now)
    finished_at: datetime | None = None
    operator: str = ""
    ports: list[PortStatus] = field(default_factory=list)
    overall_verdict: PortVerdict = PortVerdict.SKIP
    comments: str = ""
