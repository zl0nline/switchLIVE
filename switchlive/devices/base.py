"""Базовые интерфейсы адаптеров и профилей устройств.

Профиль — статическое описание модели (порты, команды, возможности).
Адаптер — реализация парсинга CLI-вывода и выполнения команд.

Новое семейство/вендор добавляется через devices/<vendor>/ —
core менять не нужно.
"""

from __future__ import annotations

import abc

from switchlive.core.models import DeviceIdentity, MacEntry, PortInfo
from switchlive.sessions.base import DeviceSession


class DeviceProfile(abc.ABC):
    """Статическое описание возможностей модели устройства.

    Подклассы заполняют атрибуты конкретными значениями для модели.
    Команды — шаблоны строк, где {port} подставляется имя порта.
    """

    # --- Идентификация ---
    vendor: str = "unknown"
    model: str = "unknown"
    family: str = ""  # группа совместимых моделей
    category: str = "switch"

    # --- Prompt / Paging ---
    prompt_vendor: str = "generic"  # ключ в COMMAND_PROMPTS
    disable_paging_cmd: str = ""    # команда отключения пейджера

    # --- Serial defaults ---
    default_baudrate: int = 9600

    # --- Возможности ---
    supports_poe: bool = False
    supports_sfp: bool = False
    supports_dom: bool = False
    supports_counters: bool = True
    supports_reset: bool = True

    # --- Команды идентификации ---
    show_version_cmd: str = "show version"
    show_serial_cmd: str = ""  # если serial отдельно от version

    # --- Команды портов ---
    show_ports_cmd: str = "show ports"
    show_macs_cmd: str = "show fdb"
    show_counters_cmd: str = "show ports {port} counters"

    # --- Управление портами ---
    shutdown_cmd: str = "config ports {port} state disable"
    no_shutdown_cmd: str = "config ports {port} state enable"

    # --- PoE ---
    show_poe_cmd: str = ""
    poe_enable_cmd: str = ""

    # --- SFP/DOM ---
    show_transceiver_cmd: str = ""

    # --- Сброс ---
    factory_reset_cmd: str = ""
    save_config_cmd: str = "save"
    reload_cmd: str = "reboot"

    @property
    @abc.abstractmethod
    def ports(self) -> list[PortInfo]:
        """Список физических портов устройства."""


class DeviceDetector(abc.ABC):
    """Детектор устройства: определяет vendor/model по выводу CLI.

    Каждый вендор реализует свой детектор.
    Discovery пробует все зарегистрированные детекторы.
    """

    @abc.abstractmethod
    def can_detect(self, session: DeviceSession) -> bool:
        """Быстрая проверка — наше ли это устройство."""

    @abc.abstractmethod
    def identify(self, session: DeviceSession) -> DeviceIdentity:
        """Полная идентификация: vendor, model, serial, firmware."""


class DeviceAdapter(abc.ABC):
    """Поведение устройства: команды и парсинг CLI-вывода."""

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
    def get_mac_table(self, session: DeviceSession) -> list[MacEntry]:
        """Возвращает список MacEntry: mac, port_index, vlan."""

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
