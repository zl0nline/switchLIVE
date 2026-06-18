"""Tests for raw serial console probing."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from switchlive.app.console_probe import (
    _classify_raw_console,
    baudrates_from_config,
    format_probe_report,
    parse_baudrates,
    probe_console,
    write_probe_samples,
)
from switchlive.config import Config
from switchlive.core.errors import TransportError


class FakeProbeTransport:
    responses: dict[tuple[str, int], bytes] = {}
    opened: list[tuple[str, int]] = []
    writes: list[tuple[str, int, bytes]] = []

    def __init__(self, port: str, baudrate: int, **_kwargs) -> None:
        self.port = port
        self.baudrate = baudrate
        self._open = False

    def open(self) -> None:
        if self.port == "/dev/ttyBAD":
            raise TransportError("cannot open")
        self._open = True
        self.opened.append((self.port, self.baudrate))

    def close(self) -> None:
        self._open = False

    def write(self, data: bytes) -> None:
        self.writes.append((self.port, self.baudrate, data))

    def read_until_idle(self, _timeout: float) -> bytes:
        return self.responses.get((self.port, self.baudrate), b"")


def test_parse_baudrates_accepts_comma_and_space_list():
    assert parse_baudrates("9600, 115200 57600") == (9600, 115200, 57600)


def test_parse_baudrates_rejects_empty():
    with pytest.raises(ValueError):
        parse_baudrates("")


def test_baudrates_from_config_uses_serial_defaults():
    config = Config.from_dict({"serial": {"default_baudrates": [9600, "115200", 9600]}})

    assert baudrates_from_config(config) == (9600, 115200)


def test_classifies_readable_prompt():
    status, readable, sample, raw_hex = _classify_raw_console(b"\r\nDGS-3000-10TC:admin#")

    assert status == "readable"
    assert readable is True
    assert "DGS-3000" in sample
    assert raw_hex


def test_classifies_garbled_wrong_baudrate():
    status, readable, _sample, raw_hex = _classify_raw_console(b"\x10b\xff\x00\\BH\x90\x1c")

    assert status == "garbled"
    assert readable is False
    assert raw_hex


def test_probe_console_checks_every_port_and_baudrate():
    FakeProbeTransport.responses = {
        ("/dev/ttyUSB0", 9600): b"\x10b\xff\x00\\BH\x90\x1c",
        ("/dev/ttyUSB0", 115200): b"\r\nDGS-3000-10TC:admin#",
    }
    FakeProbeTransport.opened = []
    FakeProbeTransport.writes = []

    with patch("switchlive.app.console_probe.SerialTransport", FakeProbeTransport):
        results = probe_console(ports=["/dev/ttyUSB0"], baudrates=(9600, 115200), timeout=0.5)

    assert [(result.baudrate, result.status) for result in results] == [
        (9600, "garbled"),
        (115200, "readable"),
    ]
    assert FakeProbeTransport.writes == [
        ("/dev/ttyUSB0", 9600, b"\r\n"),
        ("/dev/ttyUSB0", 115200, b"\r\n"),
    ]


def test_probe_console_auto_lists_serial_ports():
    FakeProbeTransport.responses = {("/dev/ttyUSB0", 9600): b"User Name:"}
    port = SimpleNamespace(name="/dev/ttyUSB0")

    with patch("switchlive.app.console_probe.list_serial_ports", return_value=[port]):
        with patch("switchlive.app.console_probe.SerialTransport", FakeProbeTransport):
            results = probe_console(baudrates=(9600,), timeout=0.5)

    assert results[0].port == "/dev/ttyUSB0"
    assert results[0].readable is True


def test_probe_console_reports_open_error():
    with patch("switchlive.app.console_probe.SerialTransport", FakeProbeTransport):
        results = probe_console(ports=["/dev/ttyBAD"], baudrates=(9600,))

    assert results[0].status == "error"
    assert "cannot open" in results[0].error


def test_format_probe_report_includes_statuses():
    FakeProbeTransport.responses = {
        ("/dev/ttyUSB0", 9600): b"",
        ("/dev/ttyUSB0", 115200): b"switch>",
    }
    with patch("switchlive.app.console_probe.SerialTransport", FakeProbeTransport):
        results = probe_console(ports=["/dev/ttyUSB0"], baudrates=(9600, 115200))

    report = format_probe_report(results)

    assert "/dev/ttyUSB0 @ 9600: SILENT" in report
    assert "/dev/ttyUSB0 @ 115200: READABLE" in report


def test_write_probe_samples_only_writes_non_empty_results(tmp_path):
    FakeProbeTransport.responses = {
        ("/dev/ttyUSB0", 9600): b"",
        ("/dev/ttyUSB0", 115200): b"switch>",
    }
    with patch("switchlive.app.console_probe.SerialTransport", FakeProbeTransport):
        results = probe_console(ports=["/dev/ttyUSB0"], baudrates=(9600, 115200))

    written = write_probe_samples(results, tmp_path)

    assert len(written) == 1
    assert "115200" in written[0].name
    assert "switch>" in written[0].read_text(encoding="utf-8")
