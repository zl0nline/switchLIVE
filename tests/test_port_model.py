"""Тесты port model (#7)."""

from __future__ import annotations

import pytest

from switchlive.core.models import (
    AdminStatus,
    LinkStatus,
    MacEntry,
    PortCounters,
    PortInfo,
    PortType,
    _media_to_type,
)


class TestPortInfo:
    def test_minimal(self):
        p = PortInfo(index=1)
        assert p.index == 1
        assert p.name == "1"
        assert p.cli_name == "1"
        assert p.type == PortType.UNKNOWN

    def test_with_names(self):
        p = PortInfo(index=5, name="Port 5", cli_name="Gi0/5")
        assert p.name == "Port 5"
        assert p.cli_name == "Gi0/5"

    def test_media_to_type_copper(self):
        p = PortInfo(index=1, media="copper")
        assert p.type == PortType.COPPER

    def test_media_to_type_sfp(self):
        p = PortInfo(index=1, media="sfp")
        assert p.type == PortType.SFP

    def test_media_to_type_sfp_plus(self):
        p = PortInfo(index=1, media="sfp+")
        assert p.type == PortType.SFP_PLUS

    def test_media_to_type_combo(self):
        p = PortInfo(index=1, media="combo")
        assert p.type == PortType.COMBO

    def test_explicit_type_overrides_media(self):
        p = PortInfo(index=1, media="copper", type=PortType.MANAGEMENT)
        assert p.type == PortType.MANAGEMENT

    def test_poe_flag(self):
        p = PortInfo(index=1, supports_poe=True)
        assert p.supports_poe is True

    def test_status_defaults(self):
        p = PortInfo(index=1)
        assert p.admin_status == AdminStatus.UNKNOWN
        assert p.link_status == LinkStatus.UNKNOWN


class TestMediaToType:
    @pytest.mark.parametrize(
        "media,expected",
        [
            ("copper", PortType.COPPER),
            ("RJ45", PortType.COPPER),
            ("UTP", PortType.COPPER),
            ("sfp", PortType.SFP),
            ("SFP", PortType.SFP),
            ("fiber", PortType.SFP),
            ("LC", PortType.SFP),
            ("sfp+", PortType.SFP_PLUS),
            ("sfp_plus", PortType.SFP_PLUS),
            ("10g", PortType.SFP_PLUS),
            ("combo", PortType.COMBO),
            ("management", PortType.MANAGEMENT),
            ("mgmt", PortType.MANAGEMENT),
            ("console", PortType.CONSOLE),
            ("unknown_xyz", PortType.UNKNOWN),
        ],
    )
    def test_media_mapping(self, media, expected):
        assert _media_to_type(media) == expected


class TestMacEntry:
    def test_basic(self):
        e = MacEntry(mac="00:11:22:33:44:55", port_index=5)
        assert e.mac == "00:11:22:33:44:55"
        assert e.port_index == 5
        assert e.vlan == 1

    def test_with_vlan(self):
        e = MacEntry(mac="AA:BB:CC:DD:EE:FF", port_index=1, vlan=100)
        assert e.vlan == 100


class TestPortCounters:
    def test_defaults(self):
        c = PortCounters()
        assert c.crc == 0
        assert c.drops == 0
        assert c.rx_bytes == 0

    def test_with_values(self):
        c = PortCounters(crc=5, drops=10, rx_packets=1000)
        assert c.crc == 5
        assert c.rx_packets == 1000
