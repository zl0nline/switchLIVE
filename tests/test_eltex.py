"""Tests for Eltex MES profiles and parsers."""

from __future__ import annotations

import pytest

from switchlive.core.credentials import Credentials
from switchlive.devices.eltex.adapter import EltexAdapter
from switchlive.devices.eltex.detector import EltexDetector
from switchlive.devices.eltex.parsers import (
    parse_counters,
    parse_mac_table,
    parse_show_inventory,
    parse_show_interfaces_status,
    parse_show_version,
    parse_transceiver,
)
from switchlive.devices.eltex.profiles import (
    MODEL_MAP,
    EltexMES2324B,
    EltexMES2324FB,
    EltexMES3300,
    get_profile_for_model,
)
from switchlive.sessions.cli_session import CLISession
from tests.test_transport import MockTransport


class TestEltexProfiles:
    def test_supported_models_in_map(self):
        assert "MES2324B" in MODEL_MAP
        assert "MES2324FB" in MODEL_MAP
        assert "MES3300" in MODEL_MAP

    def test_mes2324b_ports(self):
        profile = EltexMES2324B()
        ports = profile.ports
        assert len(ports) == 28
        assert ports[0].connector == "RJ45"
        assert ports[23].cli_name == "gigabitethernet 1/0/24"
        assert ports[24].connector == "SFP+"
        assert ports[24].speed_mbps == 10000

    def test_mes2324fb_ports(self):
        profile = EltexMES2324FB()
        ports = profile.ports
        assert len(ports) == 28
        assert ports[0].connector == "SFP"
        assert ports[20].media == "combo"
        assert ports[24].connector == "SFP+"

    def test_get_profile_for_model(self):
        assert isinstance(get_profile_for_model("MES2324B"), EltexMES2324B)
        assert isinstance(get_profile_for_model("MES2324FB AC"), EltexMES2324FB)
        assert get_profile_for_model("MES2308") is None

    def test_get_profile_mes3300(self):
        profile = get_profile_for_model("MES3300")
        assert isinstance(profile, EltexMES3300)
        assert len(profile.ports) == 28

    def test_mes3300_ports(self):
        profile = EltexMES3300()
        ports = profile.ports
        assert len(ports) == 28
        assert ports[0].connector == "RJ45"
        assert ports[24].connector == "SFP+"
        assert ports[24].speed_mbps == 10000

    def test_mes_cli_commands(self):
        profile = EltexMES2324B()
        assert profile.show_counters_cmd == "show interface counters {port}"
        assert profile.show_transceiver_cmd == "show fiber-ports optical-transceiver interface {port}"


class TestEltexParsers:
    def test_parse_show_version(self):
        output = """
        Eltex MES Ethernet Switch
        Device description: MES2324FB
        SW version: 4.0.16.134
        Serial Number: ELTX123456
        """
        identity = parse_show_version(output)
        assert identity.vendor == "Eltex"
        assert identity.model == "MES2324FB"
        assert identity.serial == "ELTX123456"
        assert identity.firmware == "4.0.16.134"

    def test_parse_show_version_model_fallback(self):
        identity = parse_show_version("MES2324B software version text")
        assert identity.model == "MES2324B"

    def test_parse_show_version_mes3300_from_firmware(self):
        """MES3300 определяем по имени прошивки, не только по Device description."""
        output = """
Active-image: flash://system/images/mes3300-4020-R3.ros
  Version: 4.0.20
  Commit: 796ae783
console#
"""
        identity = parse_show_version(output)
        assert identity.vendor == "Eltex"
        assert identity.model == "MES3300"
        assert identity.firmware == "4.0.20"

    def test_parse_show_inventory_real_output(self):
        """Реальный вывод show inventory с MES2324 AC."""
        output = '''NAME: "1"   DESCR: "28-port 1G/10G Managed Switch"   

PID: MES2324 AC   VID: 0   SN: ES2A015942   



console#'''
        identity = parse_show_inventory(output)
        assert identity.vendor == "Eltex"
        assert identity.model == "MES2324"
        assert identity.serial == "ES2A015942"

    def test_parse_show_inventory_extracts_mes_model(self):
        """PID может быть 'MES3300-24T AC' — извлекаем MES3300."""
        output = 'PID: MES3300-24T AC   VID: 0   SN: XX123'
        identity = parse_show_inventory(output)
        assert identity.model == "MES3300"
        assert identity.serial == "XX123"

    def test_parse_show_inventory_missing(self):
        """Нет PID в выводе — model unknown."""
        output = 'DESCR: "Some switch"\r\nconsole#'
        identity = parse_show_inventory(output)
        assert identity.model == "unknown"
        assert identity.serial == "unknown"

    def test_parse_mac_table(self):
        output = """
        Vlan    Mac Address       Type      Ports
        1       aabb.ccdd.eeff    dynamic   gi1/0/5
        10      00:11:22:33:44:55 dynamic   te1/0/25
        """
        assert parse_mac_table(output) == [
            (5, "AA:BB:CC:DD:EE:FF"),
            (25, "00:11:22:33:44:55"),
        ]

    def test_parse_counters(self):
        output = """
        CRC Errors: 2
        Drops: 5
        Collisions: 0
        """
        assert parse_counters(output) == {"crc": 2, "drops": 5, "collisions": 0}

    def test_parse_transceiver(self):
        output = """
        Vendor Name: FINISAR
        Serial Number: ABC123
        RX Power: -3.2 dBm
        TX Power: -2.1 dBm
        Temperature: 36.5 C
        """
        result = parse_transceiver(output)
        assert result["vendor"] == "FINISAR"
        assert result["serial"] == "ABC123"
        assert result["rx_power"] == "-3.2"
        assert result["tx_power"] == "-2.1"
        assert result["temperature"] == "36.5"


class TestEltexParserInterfacesStatus:
    def test_parse_interfaces_status_real_output(self):
        """Реальный вывод show interfaces status с MES2324."""
        output = """Port     Type         Duplex  Speed Neg      ctrl State         
gi1/0/1  1G-Copper      --      --     --     --  Down (nc)         
gi1/0/23 1G-Copper    Full    100   Enabled  Off  Up          00,00:02:09   
te1/0/1  10G-Fiber      --      --     --     --  Down (nc)         
"""
        result = parse_show_interfaces_status(output)
        assert "gi1/0/1" in result
        assert result["gi1/0/1"]["link_state"] == "down"
        assert "gi1/0/23" in result
        assert result["gi1/0/23"]["link_state"] == "up"
        assert result["gi1/0/23"]["speed_mbps"] == 100
        assert result["gi1/0/23"]["duplex"] == "Full"
        assert "te1/0/1" in result
        assert result["te1/0/1"]["link_state"] == "down"


class TestEltexDetector:
    def test_can_detect_eltex(self):
        transport = MockTransport()
        transport.add_response(b"MES2324B#")
        transport.add_response(b"Eltex MES2324B\nMES2324B#")
        transport.open()
        session = CLISession(transport, vendor="eltex")
        session.login(Credentials())

        assert EltexDetector().can_detect(session) is True

    def test_identify(self):
        transport = MockTransport()
        transport.add_response(b"MES2324FB#")
        # show inventory (первая попытка)
        transport.add_response(
            b'NAME: "1"   DESCR: "MES2324FB"   \r\n'
            b'PID: MES2324FB   VID: 0   SN: ELTX123456   \r\n'
            b'MES2324FB#'
        )
        # show version (enrich firmware)
        transport.add_response(
            b"SW version: 4.0.16.134\n"
            b"MES2324FB#"
        )
        transport.open()
        session = CLISession(transport, vendor="eltex")
        session.login(Credentials())

        identity = EltexDetector().identify(session)
        assert identity.vendor == "Eltex"
        assert identity.model == "MES2324FB"
        assert identity.serial == "ELTX123456"
        assert identity.firmware == "4.0.16.134"


class TestEltexAdapter:
    def test_adapter_set_model(self):
        adapter = EltexAdapter()
        adapter.set_model("MES2324FB")
        assert adapter.profile.model == "MES2324FB"

    def test_adapter_list_ports(self):
        adapter = EltexAdapter(EltexMES2324FB())
        assert len(adapter.list_ports(session=None)) == 28  # type: ignore[arg-type]

    def test_shutdown_sequence(self):
        transport = MockTransport()
        transport.add_response(b"MES2324B#")
        for _ in range(5):
            transport.add_response(b"MES2324B#")
        transport.open()
        session = CLISession(transport, vendor="eltex")
        session.login(Credentials())
        adapter = EltexAdapter()

        adapter.shutdown_port(session, adapter.profile.ports[0])

        written = b"".join(transport.written)
        assert b"configure terminal" in written
        assert b"interface gigabitethernet 1/0/1" in written
        assert b"shutdown" in written

    def test_counters_command(self):
        transport = MockTransport()
        transport.add_response(b"MES2324B#")
        transport.add_response(b"CRC Errors: 2\nDrops: 0\nMES2324B#")
        transport.open()
        session = CLISession(transport, vendor="eltex")
        session.login(Credentials())
        adapter = EltexAdapter()

        adapter.get_counters(session, adapter.profile.ports[0])

        written = b"".join(transport.written)
        assert b"show interface counters gigabitethernet 1/0/1" in written

    def test_transceiver_command(self):
        transport = MockTransport()
        transport.add_response(b"MES2324B#")
        transport.add_response(b"Vendor Name: FINISAR\nMES2324B#")
        transport.open()
        session = CLISession(transport, vendor="eltex")
        session.login(Credentials())
        adapter = EltexAdapter()

        adapter.get_transceiver(session, adapter.profile.ports[24])

        written = b"".join(transport.written)
        assert b"show fiber-ports optical-transceiver interface tengigabitethernet 1/0/25" in written

    def test_factory_reset_unsupported(self):
        adapter = EltexAdapter()
        with pytest.raises(NotImplementedError):
            adapter.factory_reset(session=None)  # type: ignore[arg-type]
