"""D-Link адаптер: команды + парсинг + выполнение.

Связывает профиль (статические данные) с сессией (живое устройство).
"""

from __future__ import annotations

import logging

from switchlive.core.models import DeviceIdentity, MacEntry, PortInfo
from switchlive.devices.base import DeviceAdapter, DeviceProfile, DeviceSession
from switchlive.devices.dlink.parsers import (
    parse_counters,
    parse_mac_table,
    parse_poe_status,
    parse_show_switch,
    parse_transceiver,
)
from switchlive.devices.dlink.profiles import DLinkBase, DLinkDES12xx, get_profile_for_model

log = logging.getLogger(__name__)


class DLinkAdapter(DeviceAdapter):
    """Адаптер D-Link коммутатора.

    Создаётся после определения модели. Использует профиль для команд
    и парсеры для интерпретации вывода.
    """

    def __init__(self, profile: DLinkBase | None = None) -> None:
        self._profile = profile or DLinkDES12xx()  # безопасный дефолт

    def set_model(self, model: str) -> None:
        """Подобрать профиль под определённую модель."""
        p = get_profile_for_model(model)
        if p:
            self._profile = p
        else:
            log.warning("Unknown D-Link model: %s, using base profile", model)

    @property
    def profile(self) -> DeviceProfile:
        return self._profile

    def get_identity(self, session: DeviceSession) -> DeviceIdentity:
        result = session.run_command(self._profile.show_version_cmd)
        identity = parse_show_switch(result.output)
        # Подбираем профиль под найденную модель
        if identity.model != "unknown":
            self.set_model(identity.model)
        return identity

    def list_ports(self, session: DeviceSession) -> list[PortInfo]:
        """Возвращает список портов.

        Сначала из профиля (статические данные), при возможности
        уточняет из 'show ports'.
        """
        return self._profile.ports

    def get_mac_table(self, session: DeviceSession) -> list[MacEntry]:
        result = session.run_command(self._profile.show_macs_cmd)
        raw = parse_mac_table(result.output)
        # Конвертируем tuple в MacEntry
        return [
            MacEntry(mac=mac, port_index=port_idx)
            for port_idx, mac in raw
        ]

    def get_counters(self, session: DeviceSession, port: PortInfo) -> dict[str, int]:
        cmd = self._profile.show_counters_cmd.format(port=port.name)
        result = session.run_command(cmd)
        return parse_counters(result.output)

    def shutdown_port(self, session: DeviceSession, port: PortInfo) -> None:
        cmd = self._profile.shutdown_cmd.format(port=port.name)
        session.run_command(cmd)

    def no_shutdown_port(self, session: DeviceSession, port: PortInfo) -> None:
        cmd = self._profile.no_shutdown_cmd.format(port=port.name)
        session.run_command(cmd)

    def get_poe_status(self, session: DeviceSession, port: PortInfo) -> dict[str, str]:
        if not self._profile.supports_poe or not self._profile.show_poe_cmd:
            return {}
        cmd = self._profile.show_poe_cmd.format(port=port.name)
        result = session.run_command(cmd)
        return parse_poe_status(result.output)

    def get_transceiver(self, session: DeviceSession, port: PortInfo) -> dict[str, str]:
        if not self._profile.supports_sfp or not self._profile.show_transceiver_cmd:
            return {}
        result = session.run_command(self._profile.show_transceiver_cmd)
        return parse_transceiver(result.output)

    def factory_reset(self, session: DeviceSession) -> None:
        if self._profile.factory_reset_cmd:
            session.run_command(self._profile.factory_reset_cmd)
        session.run_command(self._profile.reload_cmd)
