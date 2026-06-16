"""Нормализованные модели данных.

Используются тестами, отчётами и UI. Не содержат vendor-специфичной логики.
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


class PortType(str, Enum):
    """Тип физического порта."""

    COPPER = "copper"
    SFP = "sfp"
    SFP_PLUS = "sfp_plus"
    COMBO = "combo"
    MANAGEMENT = "management"
    CONSOLE = "console"
    UNKNOWN = "unknown"


class AdminStatus(str, Enum):
    ENABLED = "enabled"
    DISABLED = "disabled"
    UNKNOWN = "unknown"


class LinkStatus(str, Enum):
    UP = "up"
    DOWN = "down"
    UNKNOWN = "unknown"


def _media_to_type(media: str) -> PortType:
    """Преобразовать устаревшее поле media в PortType."""
    m = media.lower().strip()
    if m in ("copper", "rj45", "utp"):
        return PortType.COPPER
    if m in ("sfp+", "sfp_plus", "sfpplus", "10g"):
        return PortType.SFP_PLUS
    if m in ("sfp", "fiber", "lc"):
        return PortType.SFP
    if m in ("combo",):
        return PortType.COMBO
    if m in ("management", "mgmt"):
        return PortType.MANAGEMENT
    if m in ("console",):
        return PortType.CONSOLE
    return PortType.UNKNOWN


@dataclass
class DeviceIdentity:
    vendor: str = "unknown"
    model: str = "unknown"
    serial: str = "unknown"
    firmware: str = "unknown"
    category: DeviceCategory = DeviceCategory.UNKNOWN


@dataclass
class PortInfo:
    """Описание физического порта устройства.

    Единственная модель порта — используется адаптерами, тестами, отчётами.
    """

    index: int
    name: str = ""
    cli_name: str = ""  # vendor CLI name

    # Тип и возможности
    type: PortType = PortType.UNKNOWN
    speed_mbps: int = 0  # max capability
    media: str = ""  # legacy compat: copper, sfp, sfp+
    connector: str = ""  # RJ45, SFP, SFP+, LC
    supports_poe: bool = False
    role: str = ""  # access, uplink, management, combo

    # Текущее состояние (заполняется при тестировании)
    admin_status: AdminStatus = AdminStatus.UNKNOWN
    link_status: LinkStatus = LinkStatus.UNKNOWN
    actual_speed: int = 0
    duplex: str = ""

    # Счётчики
    crc_errors: int = 0
    drops: int = 0
    flaps: int = 0

    def __post_init__(self) -> None:
        if not self.name:
            self.name = str(self.index)
        if not self.cli_name:
            self.cli_name = self.name
        if self.media and self.type == PortType.UNKNOWN:
            self.type = _media_to_type(self.media)


@dataclass
class PortCounters:
    """Счётчики ошибок порта — снимок в момент тестирования."""

    crc: int = 0
    drops: int = 0
    collisions: int = 0
    fcs_errors: int = 0
    alignment_errors: int = 0
    rx_bytes: int = 0
    tx_bytes: int = 0
    rx_packets: int = 0
    tx_packets: int = 0


@dataclass
class MacEntry:
    """Запись MAC-таблицы."""

    mac: str
    port_index: int
    vlan: int = 1
    port_cli_name: str = ""


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
