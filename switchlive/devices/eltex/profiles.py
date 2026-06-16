"""Eltex профили коммутаторов.

Eltex MES23xx — управляемые L2+ коммутаторы, Cisco-like CLI.
MES2324B — 24x1G RJ45, 4x1G SFP (combo)
MES2324FB — 24x1G RJ45 PoE, 4x1G SFP
"""

from __future__ import annotations

from switchlive.core.models import DeviceCategory, PortInfo
from switchlive.devices.base import DeviceProfile


class EltexBase(DeviceProfile):
    """База для Eltex MES23xx."""

    vendor = "Eltex"
    category = DeviceCategory.SWITCH.value
    prompt_vendor = "eltex"
    disable_paging_cmd = "terminal datadump"

    # Команды (Cisco-like)
    show_version_cmd = "show version"
    show_ports_cmd = "show interfaces status"
    show_macs_cmd = "show mac address-table"
    show_counters_cmd = "show interfaces {port}"
    shutdown_cmd = "interface {port}\nshutdown"
    no_shutdown_cmd = "interface {port}\nno shutdown"
    save_config_cmd = "write memory"
    reload_cmd = "reload"

    show_transceiver_cmd = "show fiber-ports optical-transceiver detailed"
    factory_reset_cmd = ""

    supports_sfp = True
    supports_dom = True


class EltexMES2324B(EltexBase):
    """MES2324B — 24x1G RJ45 + 4x1G SFP (combo)."""

    model = "MES2324B"
    family = "MES23xx"
    supports_poe = False

    @property
    def ports(self) -> list[PortInfo]:
        return [
            PortInfo(
                index=i,
                name=f"gigabitethernet 1/0/{i}",
                cli_name=f"gi1/0/{i}",
                speed_mbps=1000,
                media="copper",
                connector="RJ45",
            )
            for i in range(1, 25)
        ] + [
            PortInfo(
                index=25,
                name="gigabitethernet 1/0/25",
                cli_name="gi1/0/25",
                speed_mbps=1000,
                media="sfp",
                connector="SFP",
                role="combo",
            ),
            PortInfo(
                index=26,
                name="gigabitethernet 1/0/26",
                cli_name="gi1/0/26",
                speed_mbps=1000,
                media="sfp",
                connector="SFP",
                role="combo",
            ),
            PortInfo(
                index=27,
                name="gigabitethernet 1/0/27",
                cli_name="gi1/0/27",
                speed_mbps=1000,
                media="sfp",
                connector="SFP",
                role="combo",
            ),
            PortInfo(
                index=28,
                name="gigabitethernet 1/0/28",
                cli_name="gi1/0/28",
                speed_mbps=1000,
                media="sfp",
                connector="SFP",
                role="combo",
            ),
        ]


class EltexMES2324FB(EltexBase):
    """MES2324FB — 24x1G RJ45 PoE + 4x1G SFP."""

    model = "MES2324FB"
    family = "MES23xx"
    supports_poe = True

    show_poe_cmd = "show power inline {port}"
    poe_enable_cmd = "interface {port}\npower inline enable"

    @property
    def ports(self) -> list[PortInfo]:
        return [
            PortInfo(
                index=i,
                name=f"gigabitethernet 1/0/{i}",
                cli_name=f"gi1/0/{i}",
                speed_mbps=1000,
                media="copper",
                connector="RJ45",
                supports_poe=True,
            )
            for i in range(1, 25)
        ] + [
            PortInfo(
                index=25,
                name="gigabitethernet 1/0/25",
                cli_name="gi1/0/25",
                speed_mbps=1000,
                media="sfp",
                connector="SFP",
                role="uplink",
            ),
            PortInfo(
                index=26,
                name="gigabitethernet 1/0/26",
                cli_name="gi1/0/26",
                speed_mbps=1000,
                media="sfp",
                connector="SFP",
                role="uplink",
            ),
            PortInfo(
                index=27,
                name="gigabitethernet 1/0/27",
                cli_name="gi1/0/27",
                speed_mbps=1000,
                media="sfp",
                connector="SFP",
                role="uplink",
            ),
            PortInfo(
                index=28,
                name="gigabitethernet 1/0/28",
                cli_name="gi1/0/28",
                speed_mbps=1000,
                media="sfp",
                connector="SFP",
                role="uplink",
            ),
        ]


# Карта: строка модели → класс профиля
MODEL_MAP: dict[str, type[EltexBase]] = {
    "MES2324B": EltexMES2324B,
    "MES2324FB": EltexMES2324FB,
}


def get_profile_for_model(model_str: str) -> EltexBase | None:
    """Подобрать профиль по строке модели."""
    model_upper = model_str.upper().strip()
    if model_upper in MODEL_MAP:
        return MODEL_MAP[model_upper]()
    # По префиксу
    for key, cls in MODEL_MAP.items():
        if model_upper.startswith(key):
            return cls()
    return None
