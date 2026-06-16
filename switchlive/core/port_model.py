"""Нормализованная модель портов (#7).

Расширенный PortInfo для тестов и отчётов.
Не зависит от вендора — все vendor-специфичные имена в cli_name.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


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


@dataclass
class PortInfo:
    """Нормализованное описание порта устройства.

    Используется тестами, отчётами и UI.
    """

    # Идентификация
    index: int
    name: str  = ""  # display name: "Port 1", "1"
    cli_name: str = ""  # vendor CLI name: "1", "Gi0/1", "Port1"

    # Тип и возможности
    type: PortType = PortType.UNKNOWN
    speed_mbps: int = 0  # max capability
    media: str = ""  # copper, sfp, sfp+ (legacy compat)
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
        # Если name пустой — используем index
        if not self.name:
            self.name = str(self.index)
        # Если cli_name пустой — копируем из name
        if not self.cli_name:
            self.cli_name = self.name
        # Если media задан, выводим type из него для обратной совместимости
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
