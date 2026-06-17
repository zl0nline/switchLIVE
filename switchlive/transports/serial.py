"""Serial/COM транспорт через pyserial.

Поддержка:
- список доступных портов
- открытие с настраиваемыми параметрами
- чтение до «тишины» (idle detection)
- обработка таймаутов и ошибок
"""

from __future__ import annotations

import logging
import time

from switchlive.core.errors import TransportError
from switchlive.transports.base import CommandTransport, SerialPortInfo

log = logging.getLogger(__name__)


def is_pyserial_available() -> bool:
    """Проверить, доступен ли runtime dependency pyserial."""
    try:
        import serial  # noqa: F401, PLC0415
    except ImportError:
        return False
    return True


def list_serial_ports() -> list[SerialPortInfo]:
    """Вернуть список доступных serial/COM портов."""
    try:
        from serial.tools import list_ports  # noqa: PLC0415
    except ImportError:
        log.warning(
            "pyserial не установлен — список портов недоступен. "
            "Запустите scripts/install-linux.sh или установите switchlive через pipx."
        )
        return []

    ports = []
    for cp in list_ports.comports():
        info = SerialPortInfo(
            name=cp.device,
            description=cp.description or "",
            hwid=cp.hwid or "",
            vendor_id=getattr(cp, "vid", None) or "",
            product_id=getattr(cp, "pid", None) or "",
            serial_number=getattr(cp, "serial_number", None) or "",
        )
        ports.append(info)

    return ports


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
        idle_gap: float = 0.3,
    ) -> None:
        self.port = port
        self.baudrate = baudrate
        self.bytesize = bytesize
        self.parity = parity
        self.stopbits = stopbits
        self.timeout = timeout
        self.idle_gap = idle_gap  # пауза «тишины» = конец вывода
        self._serial = None

    def open(self) -> None:
        try:
            import serial  # noqa: PLC0415
        except ImportError as e:
            raise TransportError(
                "pyserial не установлен: pip install pyserial"
            ) from e

        try:
            self._serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=self.bytesize,
                parity=self.parity,
                stopbits=self.stopbits,
                timeout=self.timeout,
            )
            log.info("Serial port opened: %s @ %d baud", self.port, self.baudrate)
        except serial.SerialException as e:
            details = str(e)
            if "Permission denied" in details:
                details += (
                    ". Нет доступа к serial-порту: добавьте пользователя в группу dialout "
                    "и перелогиньтесь, не запускайте switchlive через sudo."
                )
            raise TransportError(f"Не удалось открыть {self.port}: {details}") from e
        except Exception as e:
            raise TransportError(f"Ошибка при открытии {self.port}: {e}") from e

    def close(self) -> None:
        if self._serial and self._serial.is_open:
            self._serial.close()
            log.info("Serial port closed: %s", self.port)
        self._serial = None

    def write(self, data: bytes) -> None:
        if not self._serial:
            raise TransportError("Соединение не открыто")
        self._serial.write(data)

    def read_until_idle(self, timeout: float) -> bytes:
        """Читать данные, пока не наступит пауза (idle_gap) без новых байтов."""
        if not self._serial:
            raise TransportError("Соединение не открыто")

        buf = bytearray()
        deadline = time.monotonic() + timeout
        last_data = time.monotonic()

        while time.monotonic() < deadline:
            chunk = self._serial.read(256)
            if chunk:
                buf.extend(chunk)
                last_data = time.monotonic()
            elif time.monotonic() - last_data > self.idle_gap:
                break

        return bytes(buf)

    def is_open(self) -> bool:
        return self._serial is not None and self._serial.is_open

    def __repr__(self) -> str:
        status = "open" if self.is_open() else "closed"
        return f"SerialTransport({self.port}@{self.baudrate}, {status})"
