"""Тесты D-Link профилей и парсеров (#6)."""

from __future__ import annotations

from switchlive.devices.dlink.adapter import DLinkAdapter
from switchlive.devices.dlink.parsers import (
    _parse_speed,
    parse_counters,
    parse_mac_table,
    parse_poe_status,
    parse_show_ports,
    parse_show_switch,
    parse_transceiver,
)
from switchlive.devices.dlink.profiles import (
    MODEL_MAP,
    DLinkDES12xx,
    DLinkDES32xx,
    DLinkDES3028,
    DLinkDGS36xx,
    DLinkDGS1210,
    DLinkDGS3000,
    DLinkDGS3100,
    DLinkDGS3120,
    DLinkDGS3420,
    DLinkDGS3612,
    DLinkDGS3627,
    get_profile_for_model,
)

# --- Тесты профилей ---

class TestProfiles:
    def test_all_supported_models_in_map(self):
        """Все модели из SUPPORTED.md есть в MODEL_MAP."""
        expected = [
            "DES-1228", "DES-3200-10", "DGS-3000-10",
            "DGS-1210-28/ME", "DGS-1210-28/SX",
            "DGS-3100-24/TC", "DGS-3120-24/SC",
            "DGS-3612", "DGS-3620/SC", "DGS-3630/SC",
            "DGS-3420/SC", "DGS-3627",
            "DES-3200", "DES-3200-C1", "DES-3028", "DES-3526",
        ]
        for model in expected:
            assert model in MODEL_MAP, f"Missing: {model}"

    def test_get_profile_exact(self):
        p = get_profile_for_model("DES-1228")
        assert p is not None
        assert p.vendor == "D-Link"
        assert p.model == "DES-1228"

    def test_get_profile_prefix(self):
        """Префиксный поиск для вариаций модели."""
        p = get_profile_for_model("DGS-1210-28/ME fast")
        assert p is not None
        assert p.family == "DGS-1210"

    def test_exact_alias_profiles_keep_model_name(self):
        for model in ("DES-3200", "DES-3200-C1", "DGS-1210-28/SX", "DGS-3630/SC"):
            p = get_profile_for_model(model)
            assert p is not None
            assert p.model == model

    def test_get_profile_unknown(self):
        assert get_profile_for_model("UNKNOWN-MODEL") is None

    def test_des1228_ports(self):
        p = DLinkDES12xx()
        ports = p.ports
        assert len(ports) == 28
        assert all(pt.speed_mbps in (100, 1000) for pt in ports)
        assert p.supports_sfp is True
        assert ports[26].media == "combo"
        assert ports[26].connector == "RJ45/SFP"

    def test_des3200_10_ports(self):
        p = DLinkDES32xx()
        ports = p.ports
        assert len(ports) == 10
        assert ports[0].speed_mbps == 100
        assert ports[7].connector == "RJ45"
        assert ports[8].media == "combo"
        assert ports[8].speed_mbps == 1000

    def test_des3028_ports(self):
        p = DLinkDES3028()
        ports = p.ports
        assert len(ports) == 28
        assert ports[23].speed_mbps == 100
        assert ports[24].connector == "RJ45"
        assert ports[26].connector == "RJ45/SFP"

    def test_dgs1210_uplinks_are_1g_sfp(self):
        p = DLinkDGS1210()
        ports = p.ports
        assert len(ports) == 28
        assert ports[24].speed_mbps == 1000
        assert ports[24].connector == "SFP"
        assert ports[27].connector == "SFP"

    def test_dgs3000_10_is_non_poe_combo(self):
        p = DLinkDGS3000()
        ports = p.ports
        assert p.supports_poe is False
        assert len(ports) == 10
        assert ports[0].supports_poe is False
        assert ports[8].media == "combo"
        assert ports[8].speed_mbps == 1000

    def test_dgs3100_24tc_ports(self):
        p = DLinkDGS3100()
        ports = p.ports
        assert p.supports_poe is False
        assert len(ports) == 24
        assert ports[19].connector == "RJ45"
        assert ports[20].connector == "RJ45/SFP"

    def test_dgs3120_24sc_ports(self):
        p = DLinkDGS3120()
        ports = p.ports
        assert p.supports_poe is False
        assert len(ports) == 24
        assert ports[0].connector == "SFP"
        assert ports[15].connector == "SFP"
        assert ports[16].connector == "RJ45/SFP"

    def test_dgs36xx_sc_fiber_layout(self):
        p = DLinkDGS36xx()
        ports = p.ports
        assert p.supports_poe is False
        assert p.supports_dom is True
        assert p.show_poe_cmd == ""
        assert len(ports) == 28
        assert ports[0].connector == "SFP"
        assert ports[20].connector == "RJ45/SFP"
        assert ports[24].connector == "SFP+"

    def test_dgs3612_ports(self):
        p = DLinkDGS3612()
        ports = p.ports
        assert p.supports_poe is False
        assert len(ports) == 16
        assert ports[0].connector == "RJ45"
        assert ports[12].connector == "RJ45/SFP"

    def test_dgs3627_ports(self):
        p = DLinkDGS3627()
        ports = p.ports
        assert p.supports_poe is False
        assert len(ports) == 28
        assert ports[23].connector == "RJ45"
        assert ports[24].connector == "RJ45/SFP"

    def test_dgs3420_ports(self):
        p = DLinkDGS3420()
        ports = p.ports
        assert p.supports_poe is False
        assert len(ports) == 26  # 20 SFP + 4 combo + 2 SFP+
        assert ports[0].connector == "SFP"
        assert ports[20].connector == "RJ45/SFP"
        assert ports[24].connector == "SFP+"

    def test_base_disable_paging(self):
        p = DLinkDES12xx()
        assert p.disable_paging_cmd == "disable clipaging"

    def test_all_profiles_have_prompt_vendor(self):
        for model, cls in MODEL_MAP.items():
            p = cls()
            assert p.prompt_vendor == "dlink", f"{model}: {p.prompt_vendor}"


# --- Тесты парсеров ---

class TestParsers:
    def test_parse_show_switch(self):
        output = """
        Device Type: DES-1228
        Hardware Version: A1
        Firmware Version: 2.00.B01
        Serial Number: PZA00AB00001
        """
        ident = parse_show_switch(output)
        assert ident.vendor == "D-Link"
        assert ident.model == "DES-1228"
        assert ident.serial == "PZA00AB00001"
        assert ident.firmware == "2.00.B01"

    def test_parse_show_switch_empty(self):
        ident = parse_show_switch("garbage output")
        assert ident.model == "unknown"
        assert ident.serial == "unknown"

    def test_parse_show_ports(self):
        output = """
        Port   State/Link  Speed   Duplex
        1      Enabled/Up  100M    Full
        2      Enabled/Up  1G      Full
        25     Disabled    --      --
        """
        ports = parse_show_ports(output)
        assert len(ports) >= 2
        assert ports[0].name == "1"
        assert ports[0].speed_mbps == 100

    def test_parse_mac_table(self):
        output = """
        VLAN    MAC Address     Port
        1       00-1A-2B-3C-4D-5E  5
        1       00-50-BA-12-34-56  1
        """
        entries = parse_mac_table(output)
        assert len(entries) == 2
        assert entries[0] == (5, "00:1A:2B:3C:4D:5E")
        assert entries[1] == (1, "00:50:BA:12:34:56")

    def test_parse_counters(self):
        output = """
        CRC Errors: 5
        Drops: 12
        Collisions: 0
        """
        counters = parse_counters(output)
        assert counters["crc"] == 5
        assert counters["drops"] == 12
        assert counters["collisions"] == 0

    def test_parse_counters_empty(self):
        counters = parse_counters("no counters here")
        assert counters == {}

    def test_parse_poe_status(self):
        output = """
        PoE Status: ON
        Class: 3
        Power: 15.4 W
        """
        result = parse_poe_status(output)
        assert result["status"] == "ON"
        assert result["class"] == "3"
        assert result["power_w"] == "15.4"

    def test_parse_transceiver(self):
        output = """
        Vendor: Finisar Corp.
        Serial Number: U1234ABC
        RX Power: -3.5
        TX Power: -2.1
        Temperature: 35.2
        """
        result = parse_transceiver(output)
        assert result["vendor"] == "Finisar Corp."
        assert result["serial"] == "U1234ABC"
        assert result["rx_power"] == "-3.5"
        assert result["tx_power"] == "-2.1"
        assert result["temperature"] == "35.2"

    def test_parse_speed(self):
        assert _parse_speed("100M") == 100
        assert _parse_speed("1G") == 1000
        assert _parse_speed("10G") == 10000
        assert _parse_speed("100") == 100
        assert _parse_speed("--") == 0


# --- Тесты адаптера ---

class TestDLinkAdapter:
    def test_adapter_init(self):
        adapter = DLinkAdapter()
        assert adapter.profile is not None
        assert adapter.profile.vendor == "D-Link"

    def test_adapter_set_model(self):
        adapter = DLinkAdapter()
        adapter.set_model("DES-1228")
        assert adapter.profile.model == "DES-1228"
        assert len(adapter.profile.ports) == 28

    def test_adapter_set_unknown_model(self):
        adapter = DLinkAdapter()
        adapter.set_model("UNKNOWN-999")
        # Не падает, остаётся DES-1228 (дефолтный профиль)
        assert adapter.profile.vendor == "D-Link"

    def test_adapter_list_ports(self):
        adapter = DLinkAdapter()
        adapter.set_model("DGS-3420/SC")
        ports = adapter.list_ports(session=None)  # type: ignore[arg-type]
        assert len(ports) == 26
