"""Tests for SFP/SFP+ probe (#12)."""

from __future__ import annotations

from unittest.mock import MagicMock

from switchlive.app.sfp import (
    SfpResult,
    SfpVerdict,
    _normalize_sfp,
    evaluate_sfp_result,
    probe_sfp_status,
)
from switchlive.app.walk_test import WalkTestConfig, WalkTestEngine
from switchlive.core.models import MacEntry, PortInfo, PortType, PortVerdict


class TestNormalizeSfp:
    def test_full_dom(self):
        result = _normalize_sfp(
            {
                "vendor": "Finisar",
                "serial": "ABC123",
                "rx_power": "-3.5",
                "tx_power": "-2.1",
                "temperature": "35.2",
            }
        )
        assert result.present is True
        assert result.dom_supported is True
        assert result.vendor == "Finisar"
        assert result.serial == "ABC123"
        assert result.rx_power_dbm == -3.5
        assert result.tx_power_dbm == -2.1
        assert result.temperature_c == 35.2

    def test_metadata_without_dom(self):
        result = _normalize_sfp({"vendor": "DAC", "serial": "D123"})
        assert result.present is True
        assert result.dom_supported is False

    def test_empty(self):
        result = _normalize_sfp({})
        assert result.present is False
        assert result.dom_supported is False


class TestEvaluateSfp:
    def test_full_dom_pass(self):
        sfp = SfpResult(
            present=True,
            dom_supported=True,
            vendor="Finisar",
            serial="ABC123",
            rx_power_dbm=-3.5,
        )
        result = evaluate_sfp_result(sfp)
        assert result.verdict == SfpVerdict.PASS

    def test_metadata_without_dom_warn(self):
        sfp = SfpResult(present=True, dom_supported=False, vendor="DAC")
        result = evaluate_sfp_result(sfp)
        assert result.verdict == SfpVerdict.WARN
        assert any("DOM" in note for note in result.notes)

    def test_not_present_warn(self):
        result = evaluate_sfp_result(SfpResult())
        assert result.verdict == SfpVerdict.WARN


class TestProbeSfp:
    def test_non_sfp_port_skip(self):
        adapter = MagicMock()
        port = PortInfo(index=1, name="1", type=PortType.COPPER)
        result = probe_sfp_status(adapter, MagicMock(), port)
        assert result.verdict == SfpVerdict.SKIP

    def test_adapter_without_transceiver_warn(self):
        adapter = MagicMock(spec=["get_mac_table"])
        port = PortInfo(index=25, name="25", type=PortType.SFP)
        result = probe_sfp_status(adapter, MagicMock(), port)
        assert result.verdict == SfpVerdict.WARN

    def test_adapter_empty_response_warn(self):
        adapter = MagicMock()
        adapter.get_transceiver.return_value = {}
        port = PortInfo(index=25, name="25", type=PortType.SFP)
        result = probe_sfp_status(adapter, MagicMock(), port)
        assert result.verdict == SfpVerdict.WARN

    def test_adapter_full_dom_pass(self):
        adapter = MagicMock()
        adapter.get_transceiver.return_value = {
            "vendor": "Finisar",
            "serial": "ABC123",
            "rx_power": "-3.5",
            "tx_power": "-2.1",
            "temperature": "35.2",
        }
        port = PortInfo(index=25, name="25", type=PortType.SFP_PLUS)
        result = probe_sfp_status(adapter, MagicMock(), port)
        assert result.verdict == SfpVerdict.PASS


class TestWalkTestSfpIntegration:
    def _make_adapter(self, transceiver_raw):
        adapter = MagicMock()
        adapter.get_mac_table.side_effect = [
            [],
            [MacEntry(mac="AA:BB:CC:DD:EE:01", port_index=25)],
        ]
        adapter.get_counters.return_value = {"crc": 0, "drops": 0}
        adapter.get_transceiver.return_value = transceiver_raw
        adapter.shutdown_port.return_value = None
        return adapter

    def test_sfp_dom_pass_keeps_port_pass(self):
        port = PortInfo(index=25, name="25", type=PortType.SFP_PLUS)
        adapter = self._make_adapter(
            {
                "vendor": "Finisar",
                "serial": "ABC123",
                "rx_power": "-3.5",
                "tx_power": "-2.1",
                "temperature": "35.2",
            }
        )

        engine = WalkTestEngine(
            adapter,
            MagicMock(),
            WalkTestConfig(detection_retries=1, detection_delay=0),
        )
        result = engine.run(ports=[port], progress_callback=lambda s, m: None)[0]

        assert result.verdict == PortVerdict.PASS
        assert result.sfp is not None
        assert any("SFP: PASS" in note for note in result.notes)

    def test_sfp_missing_dom_warns_without_crash(self):
        port = PortInfo(index=25, name="25", type=PortType.SFP_PLUS)
        adapter = self._make_adapter({"vendor": "DAC", "serial": "D123"})

        engine = WalkTestEngine(
            adapter,
            MagicMock(),
            WalkTestConfig(detection_retries=1, detection_delay=0),
        )
        result = engine.run(ports=[port], progress_callback=lambda s, m: None)[0]

        assert result.verdict == PortVerdict.WARN
        assert any("SFP: WARN" in note for note in result.notes)
        assert any("DOM metrics" in note for note in result.notes)
