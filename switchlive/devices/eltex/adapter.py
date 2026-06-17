"""Eltex adapter: commands + parsers."""

from __future__ import annotations

import logging

from switchlive.core.models import DeviceIdentity, MacEntry, PortInfo
from switchlive.devices.base import DeviceAdapter, DeviceProfile, DeviceSession
from switchlive.devices.eltex.parsers import (
    parse_counters,
    parse_mac_table,
    parse_show_interfaces_status,
    parse_show_version,
    parse_transceiver,
)
from switchlive.devices.eltex.profiles import EltexBase, EltexMES2324B, get_profile_for_model
from switchlive.core.models import LinkStatus

log = logging.getLogger(__name__)


class EltexAdapter(DeviceAdapter):
    """Adapter for Eltex MES switches."""

    def __init__(self, profile: EltexBase | None = None) -> None:
        self._profile = profile or EltexMES2324B()

    def set_model(self, model: str) -> None:
        profile = get_profile_for_model(model)
        if profile:
            self._profile = profile
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
        """Return ports with live link status from show interfaces status."""
        ports = list(self._profile.ports)
        try:
            result = session.run_command(self._profile.show_ports_cmd)
            live_status = parse_show_interfaces_status(result.output)
            for port in ports:
                key = port.cli_name.lower().replace(" ", "")
                info = live_status.get(key)
                if info:
                    if info["link_state"] == "up":
                        port.link_status = LinkStatus.UP
                    else:
                        port.link_status = LinkStatus.DOWN
                    if info["speed_mbps"]:
                        port.actual_speed = info["speed_mbps"]
                    if info["duplex"] and info["duplex"] != "--":
                        port.duplex = info["duplex"].lower()
        except Exception as e:
            log.warning("Failed to refresh port status: %s", e)
        return ports

    def get_mac_table(self, session: DeviceSession) -> list[MacEntry]:
        result = session.run_command(self._profile.show_macs_cmd)
        return [
            MacEntry(mac=mac, port_index=port_idx)
            for port_idx, mac in parse_mac_table(result.output)
        ]

    def get_counters(self, session: DeviceSession, port: PortInfo) -> dict[str, int]:
        cmd = self._profile.show_counters_cmd.format(port=port.cli_name)
        result = session.run_command(cmd)
        return parse_counters(result.output)

    def shutdown_port(self, session: DeviceSession, port: PortInfo) -> None:
        self._set_port_shutdown(session, port, shutdown=True)

    def no_shutdown_port(self, session: DeviceSession, port: PortInfo) -> None:
        self._set_port_shutdown(session, port, shutdown=False)

    def get_poe_status(self, session: DeviceSession, port: PortInfo) -> dict[str, str]:
        return {}

    def get_transceiver(self, session: DeviceSession, port: PortInfo) -> dict[str, str]:
        if not self._profile.supports_sfp or not self._profile.show_transceiver_cmd:
            return {}
        result = session.run_command(self._profile.show_transceiver_cmd.format(port=port.cli_name))
        return parse_transceiver(result.output)

    def factory_reset(self, session: DeviceSession) -> None:
        raise NotImplementedError("factory reset unsupported for Eltex MES profile")

    def _set_port_shutdown(
        self,
        session: DeviceSession,
        port: PortInfo,
        *,
        shutdown: bool,
    ) -> None:
        session.run_command("configure terminal")
        session.run_command(f"interface {port.cli_name}")
        session.run_command("shutdown" if shutdown else "no shutdown")
        session.run_command("exit")
        session.run_command("exit")
