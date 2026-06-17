"""Базовый интерфейс транспорта.

Транспорт — минимальный канал байтов к устройству.
Не знает про вендоров, промпты, команды — только байты.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass


@dataclass
class SerialPortInfo:
    """Информация о доступном serial/COM-порту."""

    name: str  # /dev/ttyUSB0, COM3, ...
    description: str = ""
    hwid: str = ""
    vendor_id: str = ""
    product_id: str = ""
    serial_number: str = ""


class CommandTransport(abc.ABC):
    """Транспорт: соединение с устройством на уровне байтов."""

    @abc.abstractmethod
    def open(self) -> None:
        """Установить соединение."""

    @abc.abstractmethod
    def close(self) -> None:
        """Закрыть соединение."""

    @abc.abstractmethod
    def write(self, data: bytes) -> None:
        """Отправить байты."""

    @abc.abstractmethod
    def read_until_idle(self, timeout: float) -> bytes:
        """Читать до наступления «тишины» в канале.

        Читает данные, пока не наступит пауза (idle_gap) без новых байтов
        или не истечёт timeout.
        """

    def reset_input_buffer(self) -> None:
        """Сбросить входной буфер транспорта (по умолчанию: noop)."""


    @abc.abstractmethod
    def is_open(self) -> bool:
        """Соединение активно."""

    # Удобные методы (реализованы через write + read)

    def send_line(self, text: str, timeout: float = 10.0) -> bytes:
        """Отправить строку + \\r\\n и прочитать ответ."""
        self.write(text.encode() + b"\r\n")
        return self.read_until_idle(timeout)

    def send_newline(self, timeout: float = 5.0) -> bytes:
        """Отправить пустую строку (Enter) и прочитать ответ."""
        self.write(b"\r\n")
        return self.read_until_idle(timeout)
