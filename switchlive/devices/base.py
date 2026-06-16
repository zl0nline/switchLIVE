"""Базовые интерфейсы адаптеров и профилей устройств."""

from __future__ import annotations

import abc

from switchlive.core.models import DeviceIdentity, PortInfo
from switchlive.sessions.base import DeviceSession


class DeviceProfile(abc.ABC):
    """Статическое описание возможностей устройства."""

    vendor: str = "unknown"
    model: str = "unknown"
    category: str = "unknown"
    prompt_vendor: str = "generic"

    # Возможности
    supports_poe: bool = False
    supports_sfp: bool = False
    supports_dom: bool = False
    supports_counters: bool = True
    supports_reset: bool = True

    # Настройки serial по умолчанию
    default_baudrate: int = 9600

    @property
    @abc.abstractmethod
    def ports(self) -> list[PortInfo]:
        """Список портов устройства."""


class DeviceAdapter(abc.ABC):
    """Поведение устройства: команды и парсинг."""

    @property
    @abc.abstractmethod
    def profile(self) -> DeviceProfile:
        ...

    @abc.abstractmethod
    def get_identity(self, session: DeviceSession) -> DeviceIdentity:
        ...

    @abc.abstractmethod
    def list_ports(self, session: DeviceSession) -> list[PortInfo]:
        ...

    @abc.abstractmethod
    def get_mac_table(self, session: DeviceSession) -> list[tuple[int, str]]:
        """Возвращает [(port_index, mac_address), ...]"""

    @abc.abstractmethod
    def get_counters(self, session: DeviceSession, port: PortInfo) -> dict[str, int]:
        """Возвращает словарь счётчиков: crc, drops, etc."""

    @abc.abstractmethod
    def shutdown_port(self, session: DeviceSession, port: PortInfo) -> None:
        ...

    @abc.abstractmethod
    def no_shutdown_port(self, session: DeviceSession, port: PortInfo) -> None:
        ...

    @abc.abstractmethod
    def factory_reset(self, session: DeviceSession) -> None:
        ...
