"""Eltex адаптер: команды + парсинг + выполнение."""

from __future__ import annotations

import logging

from switchlive.core.models import DeviceIdentity, MacEntry, PortInfo
from switchlive.devices.base import DeviceAdapter, DeviceProfile, DeviceSession
from switchlive.devices.eltex.parsers import (
    parse_counters,
    parse_mac_table,
    parse_poe_status,
    parse_show_version,
    parse_transceiver,
)
from switchlive.devices.eltex.profiles import EltexBase, EltexMES2324B, get_profile_for_model

log = logging.getLogger(__name__)


class EltexAdapter(DeviceAdapter):
    """Адаптер Eltex MES23xx."""

    def __init__(self, profile: EltexBase | None = None) -> None:
        self._profile = profile or EltexMES2324B()

    def set_model(self, model: str) -> None:
        p = get_profile_for_model(model)
        if p:
            self._profile = p
        else:
            log.warning("Unknown Eltex model: %s, using base profile", model)

    @property
    def profile(self) -> DeviceProfile:
        return self._profile

    def get_identity(self, session: DeviceSession) -> DeviceIdentity:
        result = session.run_command(self._profile.show_version_cmd)
        identity = parse_show_version(result.output)
        if identity.model != "unknown":
            self.set_model(identity.model)
        return identity

    def list_ports(self, session: DeviceSession) -> list[PortInfo]:
        return self._profile.ports

    def get_mac_table(self, session: DeviceSession) -> list[MacEntry]:
        result = session.run_command(self._profile.show_macs_cmd)
        raw = parse_mac_table(result.output)
        return [
            MacEntry(mac=mac, port_index=port_idx)
            for port_idx, mac in raw
        ]

    def get_counters(self, session: DeviceSession, port: PortInfo) -> dict[str, int]:
        cmd = self._profile.show_counters_cmd.format(port=port.cli_name)
        result = session.run_command(cmd)
        return parse_counters(result.output)

    def shutdown_port(self, session: DeviceSession, port: PortInfo) -> None:
        cmd = self._profile.shutdown_cmd.format(port=port.cli_name)
        for line in cmd.split("\n"):
            session.run_command(line)

    def no_shutdown_port(self, session: DeviceSession, port: PortInfo) -> None:
        cmd = self._profile.no_shutdown_cmd.format(port=port.cli_name)
        for line in cmd.split("\n"):
            session.run_command(line)

    def get_poe_status(self, session: DeviceSession, port: PortInfo) -> dict[str, str]:
        if not self._profile.supports_poe or not self._profile.show_poe_cmd:
            return {}
        cmd = self._profile.show_poe_cmd.format(port=port.cli_name)
        result = session.run_command(cmd)
        return parse_poe_status(result.output)

    def get_transceiver(self, session: DeviceSession, port: PortInfo) -> dict[str, str]:
        if not self._profile.supports_sfp or not self._profile.show_transceiver_cmd:
            return {}
        result = session.run_command(self._profile.show_transceiver_cmd)
        return parse_transceiver(result.output)

    def factory_reset(self, session: DeviceSession) -> None:
        # Eltex: нет одной команды reset config
        # Последовательность: erase startup-config + reload
        session.run_command("erase startup-config")
        session.run_command(self._profile.reload_cmd)
