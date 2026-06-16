"""Serial/COM транспорт через pyserial."""

from __future__ import annotations

import time

from switchlive.core.errors import TransportError
from switchlive.transports.base import CommandTransport


class SerialTransport(CommandTransport):
    """Транспорт через USB-UART / RJ45-serial консольный кабель."""

    def __init__(
        self,
        port: str,
        baudrate: int = 9600,
        bytesize: int = 8,
        parity: str = "N",
        stopbits: float = 1,
        timeout: float = 1.0,
    ) -> None:
        self.port = port
        self.baudrate = baudrate
        self.bytesize = bytesize
        self.parity = parity
        self.stopbits = stopbits
        self.timeout = timeout
        self._serial = None

    def open(self) -> None:
        try:
            import serial  # noqa: PLC0415 — отложенный импорт
        except ImportError as e:
            raise TransportError("pyserial не установлен: pip install pyserial") from e

        try:
            self._serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=self.bytesize,
                parity=self.parity,
                stopbits=self.stopbits,
                timeout=self.timeout,
            )
        except Exception as e:
            raise TransportError(f"Не удалось открыть {self.port}: {e}") from e

    def close(self) -> None:
        if self._serial and self._serial.is_open:
            self._serial.close()
        self._serial = None

    def write(self, data: bytes) -> None:
        if not self._serial:
            raise TransportError("Соединение не открыто")
        self._serial.write(data)

    def read_until_idle(self, timeout: float) -> bytes:
        if not self._serial:
            raise TransportError("Соединение не открыто")

        buf = bytearray()
        idle_gap = 0.3  # секунд тишины = конец вывода
        deadline = time.monotonic() + timeout
        last_data = time.monotonic()

        while time.monotonic() < deadline:
            chunk = self._serial.read(256)
            if chunk:
                buf.extend(chunk)
                last_data = time.monotonic()
            elif time.monotonic() - last_data > idle_gap:
                break

        return bytes(buf)

    def is_open(self) -> bool:
        return self._serial is not None and self._serial.is_open
