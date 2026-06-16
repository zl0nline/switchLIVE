"""Тесты Eltex профилей, парсеров и адаптера."""

from __future__ import annotations

from switchlive.core.credentials import Credentials
from switchlive.core.models import MacEntry
from switchlive.devices.eltex.adapter import EltexAdapter
from switchlive.devices.eltex.detector import EltexDetector
from switchlive.devices.eltex.parsers import (
    _port_name_to_index,
    parse_counters,
    parse_mac_table,
    parse_poe_status,
    parse_show_version,
    parse_transceiver,
)
from switchlive.devices.eltex.profiles import (
    MODEL_MAP,
    EltexMES2324B,
    EltexMES2324FB,
    get_profile_for_model,
)
from switchlive.devices.registry import get_all_detectors, list_detector_vendors
from switchlive.sessions.cli_session import CLISession
from tests.test_transport import MockTransport


class TestProfiles:
    def test_models_in_map(self):
        assert "MES2324B" in MODEL_MAP
        assert "MES2324FB" in MODEL_MAP

    def test_get_profile_exact(self):
        p = get_profile_for_model("MES2324B")
        assert p is not None
        assert p.vendor == "Eltex"
        assert p.model == "MES2324B"

    def test_get_profile_case_insensitive(self):
        p = get_profile_for_model("mes2324b")
        assert p is not None

    def test_get_profile_unknown(self):
        assert get_profile_for_model("UNKNOWN") is None

    def test_mes2324b_ports(self):
        p = EltexMES2324B()
        ports = p.ports
        assert len(ports) == 28  # 24 copper + 4 SFP
        assert all(pt.name.startswith("gigabitethernet") for pt in ports)
        assert ports[24].media == "sfp"

    def test_mes2324fb_poe(self):
        p = EltexMES2324FB()
        assert p.supports_poe is True
        ports = p.ports
        assert len(ports) == 28
        assert all(pt.supports_poe for pt in ports[:24])

    def test_prompt_vendor(self):
        p = EltexMES2324B()
        assert p.prompt_vendor == "eltex"

    def test_disable_paging(self):
        p = EltexMES2324B()
        assert p.disable_paging_cmd == "terminal datadump"


class TestParsers:
    def test_parse_show_version(self):
        output = """
        Machine Description: MES2324B
        Serial Number: ELTX12345678
        Software Version: 4.0.13.1
        """
        ident = parse_show_version(output)
        assert ident.vendor == "Eltex"
        assert ident.model == "MES2324B"
        assert ident.serial == "ELTX12345678"
        assert ident.firmware == "4.0.13.1"

    def test_parse_show_version_model_from_pattern(self):
        output = "Some text MES2324FB more text"
        ident = parse_show_version(output)
        assert ident.model == "MES2324FB"

    def test_parse_mac_table(self):
        output = """
        Vlan    Mac Address       Type    Ports
        1       00:1A:2B:3C:4D:5E Dyn     gi1/0/5
        1       00:50:BA:12:34:56 Dyn     gi1/0/1
        """
        entries = parse_mac_table(output)
        assert len(entries) == 2
        assert entries[0] == (5, "00:1A:2B:3C:4D:5E")
        assert entries[1] == (1, "00:50:BA:12:34:56")

    def test_parse_counters(self):
        output = "CRC: 3\nDrops: 7\nCollisions: 1"
        counters = parse_counters(output)
        assert counters["crc"] == 3
        assert counters["drops"] == 7
        assert counters["collisions"] == 1

    def test_parse_poe_status(self):
        output = "Oper Status: ON\nClass: 3\nPower consumed: 15.4 W"
        result = parse_poe_status(output)
        assert result["status"] == "ON"
        assert result["class"] == "3"
        assert result["power_w"] == "15.4"

    def test_parse_transceiver(self):
        output = """
        Vendor Name: Finisar
        Vendor Serial Number: U1234
        RX Power: -3.5
        TX Power: -2.1
        Temperature: 35.2
        """
        result = parse_transceiver(output)
        assert result["vendor"] == "Finisar"
        assert result["serial"] == "U1234"

    def test_port_name_to_index(self):
        assert _port_name_to_index("gi1/0/5") == 5
        assert _port_name_to_index("gi1/0/25") == 25
        assert _port_name_to_index("unknown") == 0


class TestAdapter:
    def test_init(self):
        adapter = EltexAdapter()
        assert adapter.profile.vendor == "Eltex"

    def test_set_model(self):
        adapter = EltexAdapter()
        adapter.set_model("MES2324FB")
        assert adapter.profile.model == "MES2324FB"
        assert adapter.profile.supports_poe is True

    def test_list_ports(self):
        adapter = EltexAdapter()
        adapter.set_model("MES2324B")
        ports = adapter.list_ports(session=None)  # type: ignore
        assert len(ports) == 28

    def test_get_mac_table_returns_macentry(self):
        from unittest.mock import MagicMock

        adapter = EltexAdapter()
        session = MagicMock()
        session.run_command.return_value = MagicMock(
            output="1  00:1A:2B:3C:4D:5E Dyn gi1/0/3"
        )
        entries = adapter.get_mac_table(session)
        assert len(entries) == 1
        assert isinstance(entries[0], MacEntry)
        assert entries[0].port_index == 3


class TestDetectorRegistry:
    def test_eltex_detector_registered(self):
        vendors = list_detector_vendors()
        assert "eltex" in vendors

    def test_get_all_detectors_has_eltex(self):
        detectors = get_all_detectors()
        assert any(isinstance(d, EltexDetector) for d in detectors)


class TestDetector:
    def test_can_detect_eltex(self):
        transport = MockTransport()
        transport.add_response(b"switch#")
        transport.add_response(
            b"Machine Description: MES2324B\nSoftware Version: 4.0.13.1\nswitch#"
        )
        transport.open()

        session = CLISession(transport, vendor="eltex")
        session.login(Credentials())

        detector = EltexDetector()
        assert detector.can_detect(session) is True

    def test_can_detect_not_eltex(self):
        transport = MockTransport()
        transport.add_response(b"switch>")
        transport.add_response(b"some random output\nswitch>")
        transport.open()

        session = CLISession(transport, vendor="generic")
        session.login(Credentials())

        detector = EltexDetector()
        assert detector.can_detect(session) is False
