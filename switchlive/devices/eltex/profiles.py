"""Eltex MES profiles."""

from __future__ import annotations

import re

from switchlive.core.models import DeviceCategory, PortInfo
from switchlive.devices.base import DeviceProfile


class EltexBase(DeviceProfile):
    """Base profile for Eltex MES switches."""

    vendor = "Eltex"
    category = DeviceCategory.SWITCH.value
    prompt_vendor = "eltex"
    disable_paging_cmd = "terminal datadump"

    default_baudrate = 115200
    supports_poe = False
    supports_sfp = True
    supports_dom = True
    supports_reset = False

    show_version_cmd = "show version"
    show_ports_cmd = "show interfaces status"
    show_macs_cmd = "show mac address-table"
    show_counters_cmd = "show interface counters {port}"
    show_transceiver_cmd = "show fiber-ports optical-transceiver interface {port}"
    reload_cmd = "reload"


class EltexMES2324B(EltexBase):
    """MES2324B — 24x1G RJ45 + 4x10G SFP+."""

    model = "MES2324B"
    family = "MES2324"

    @property
    def ports(self) -> list[PortInfo]:
        return [
            PortInfo(
                index=i,
                name=str(i),
                cli_name=f"gigabitethernet 1/0/{i}",
                speed_mbps=1000,
                media="copper",
                connector="RJ45",
            )
            for i in range(1, 25)
        ] + [
            PortInfo(
                index=i,
                name=str(i),
                cli_name=f"tengigabitethernet 1/0/{i}",
                speed_mbps=10000,
                media="sfp_plus",
                connector="SFP+",
                role="uplink",
            )
            for i in range(25, 29)
        ]


class EltexMES2324FB(EltexBase):
    """MES2324FB — 20xSFP + 4xcombo + 4x10G SFP+."""

    model = "MES2324FB"
    family = "MES2324F"

    @property
    def ports(self) -> list[PortInfo]:
        return [
            PortInfo(
                index=i,
                name=str(i),
                cli_name=f"gigabitethernet 1/0/{i}",
                speed_mbps=1000,
                media="sfp",
                connector="SFP",
            )
            for i in range(1, 21)
        ] + [
            PortInfo(
                index=i,
                name=str(i),
                cli_name=f"gigabitethernet 1/0/{i}",
                speed_mbps=1000,
                media="combo",
                connector="RJ45/SFP",
                role="combo",
            )
            for i in range(21, 25)
        ] + [
            PortInfo(
                index=i,
                name=str(i),
                cli_name=f"tengigabitethernet 1/0/{i}",
                speed_mbps=10000,
                media="sfp_plus",
                connector="SFP+",
                role="uplink",
            )
            for i in range(25, 29)
        ]


class EltexMES3300(EltexBase):
    """MES3300 series — 24x1G RJ45 + 4x10G SFP+.

    Common configurations:
      MES3300-24T: 24x1G + 4x10G SFP+
      MES3300-48T: 48x1G + 4x10G SFP+
    The exact port count may vary; we default to 24+4.
    """

    model = "MES3300"
    family = "MES3300"

    @property
    def ports(self) -> list[PortInfo]:
        return [
            PortInfo(
                index=i,
                name=str(i),
                cli_name=f"gigabitethernet 1/0/{i}",
                speed_mbps=1000,
                media="copper",
                connector="RJ45",
            )
            for i in range(1, 25)
        ] + [
            PortInfo(
                index=i,
                name=str(i),
                cli_name=f"tengigabitethernet 1/0/{i}",
                speed_mbps=10000,
                media="sfp_plus",
                connector="SFP+",
                role="uplink",
            )
            for i in range(25, 29)
        ]


MODEL_MAP: dict[str, type[EltexBase]] = {
    "MES2324B": EltexMES2324B,
    "MES2324FB": EltexMES2324FB,
    "MES3300": EltexMES3300,
}


def get_profile_for_model(model_str: str) -> EltexBase | None:
    """Return an Eltex profile by exact model or MES family prefix.

    Matching order:
    1. Exact match ("MES2324B" -> EltexMES2324B)
    2. Model starts with a known key ("MES2324FB AC" -> EltexMES2324FB)
    3. Key starts with model's numeric family ("MES2324" -> EltexMES2324B)
       Only for exact numeric-family matches, not arbitrary prefixes.
    """
    normalized = model_str.upper().strip()
    if normalized in MODEL_MAP:
        return MODEL_MAP[normalized]()

    # Model starts with a known key (e.g. "MES2324FB AC" starts with "MES2324FB")
    for key, cls in MODEL_MAP.items():
        if normalized.startswith(key):
            return cls()

    # Try stripping suffix letters from the model (e.g. "MES2324F" -> "MES2324")
    match = re.match(r"(MES\d{2,4})", normalized)
    if match:
        numeric_family = match.group(1)
        if numeric_family in MODEL_MAP:
            return MODEL_MAP[numeric_family]()

    return None
