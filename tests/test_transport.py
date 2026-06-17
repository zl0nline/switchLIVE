"""Тесты transport layer (#3)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from switchlive.core.errors import TransportError
from switchlive.transports.base import CommandTransport, SerialPortInfo
from switchlive.transports.serial import SerialTransport, list_serial_ports


def test_port_info_dataclass():
    info = SerialPortInfo(name="/dev/ttyUSB0", description="USB Serial")
    assert info.name == "/dev/ttyUSB0"
    assert info.description == "USB Serial"
    assert info.vendor_id == ""


def test_serial_transport_init():
    t = SerialTransport(port="/dev/ttyUSB0", baudrate=115200)
    assert t.port == "/dev/ttyUSB0"
    assert t.baudrate == 115200
    assert t.bytesize == 8
    assert t.parity == "N"
    assert t.stopbits == 1
    assert t.is_open() is False


def test_serial_transport_repr():
    t = SerialTransport(port="COM3")
    assert "COM3" in repr(t)
    assert "closed" in repr(t)


def test_serial_transport_not_open_write():
    t = SerialTransport(port="/dev/ttyUSB0")
    with pytest.raises(TransportError, match="не открыто"):
        t.write(b"test")


def test_serial_transport_not_open_read():
    t = SerialTransport(port="/dev/ttyUSB0")
    with pytest.raises(TransportError, match="не открыто"):
        t.read_until_idle(1.0)


def test_serial_transport_close_when_not_open():
    """close() не должен падать, если порт не был открыт."""
    t = SerialTransport(port="/dev/ttyUSB0")
    t.close()  # не должно вызвать ошибку
    assert t.is_open() is False


def test_list_serial_ports_returns_list():
    """list_serial_ports возвращает список (может быть пустым)."""
    ports = list_serial_ports()
    assert isinstance(ports, list)


def test_list_serial_ports_prefers_usb_adapters(monkeypatch):
    """Если есть USB-console, не шумим kernel ttyS0..31."""
    fake_ports = [
        SimpleNamespace(device="/dev/ttyS0", description="", hwid="", vid=None, pid=None, serial_number=None),
        SimpleNamespace(device="/dev/ttyUSB0", description="", hwid="", vid=None, pid=None, serial_number=None),
        SimpleNamespace(device="/dev/ttyS1", description="", hwid="", vid=None, pid=None, serial_number=None),
    ]

    from serial.tools import list_ports

    monkeypatch.setattr(list_ports, "comports", lambda: fake_ports)

    ports = list_serial_ports()

    assert [port.name for port in ports] == ["/dev/ttyUSB0"]


def test_command_transport_is_abstract():
    """CommandTransport — абстрактный класс."""
    with pytest.raises(TypeError):
        CommandTransport()  # type: ignore[abstract]


# --- Mock transport для тестов session ---

class MockTransport(CommandTransport):
    """Мок-транспорт с запрограммированными ответами."""

    def __init__(self, responses: list[bytes] | None = None) -> None:
        self._responses = responses or []
        self._written: list[bytes] = []
        self._open = False

    def open(self) -> None:
        self._open = True

    def close(self) -> None:
        self._open = False

    def write(self, data: bytes) -> None:
        self._written.append(data)

    def read_until_idle(self, timeout: float) -> bytes:
        if self._responses:
            return self._responses.pop(0)
        return b""

    def reset_input_buffer(self) -> None:
        pass  # mock: no-op

    def is_open(self) -> bool:
        return self._open

    @property
    def written(self) -> list[bytes]:
        return self._written

    def add_response(self, data: bytes) -> None:
        self._responses.append(data)
