"""Тесты PoE probe (#11)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from switchlive.app.poe import (
    PoEResult,
    PoEState,
    PoEVerdict,
    _normalize_poe,
    evaluate_poe_verdict,
    probe_poe_status,
    wait_for_camera,
)
from switchlive.core.models import PortInfo


class TestNormalizePoe:
    """Нормализация vendor-специфичного вывода."""

    def test_powered_on(self):
        raw = {"status": "ON", "class": "3", "power_w": "15.4"}
        result = _normalize_poe(raw)
        assert result.state == PoEState.POWERED
        assert result.powered is True
        assert result.poe_class == "3"
        assert result.power_w == 15.4

    def test_disabled(self):
        raw = {"status": "DISABLED"}
        result = _normalize_poe(raw)
        assert result.state == PoEState.DISABLED
        assert result.enabled is False

    def test_fault(self):
        raw = {"status": "FAULT", "fault": "overload"}
        result = _normalize_poe(raw)
        assert result.state == PoEState.FAULT
        assert result.fault == "overload"

    def test_searching(self):
        raw = {"status": "SEARCHING"}
        result = _normalize_poe(raw)
        assert result.state == PoEState.NOT_POWERED
        assert result.enabled is True

    def test_unknown_status(self):
        raw = {"status": "WEIRD"}
        result = _normalize_poe(raw)
        assert result.state == PoEState.UNKNOWN

    def test_power_variants(self):
        raw = {"status": "ON", "power": "12.5"}
        result = _normalize_poe(raw)
        assert result.power_w == 12.5

    def test_empty(self):
        result = _normalize_poe({})
        assert result.state == PoEState.UNKNOWN
        assert result.power_w == 0.0


class TestEvaluateVerdict:
    def test_skip_not_supported(self):
        poe = PoEResult(verdict=PoEVerdict.SKIP)
        result = evaluate_poe_verdict(poe)
        assert result.verdict == PoEVerdict.SKIP

    def test_fault_fail(self):
        poe = PoEResult(
            verdict=PoEVerdict.WARN,
            state=PoEState.FAULT,
            fault="overload",
        )
        result = evaluate_poe_verdict(poe)
        assert result.verdict == PoEVerdict.FAIL

    def test_disabled_skip(self):
        poe = PoEResult(
            verdict=PoEVerdict.WARN,
            state=PoEState.DISABLED,
        )
        result = evaluate_poe_verdict(poe)
        assert result.verdict == PoEVerdict.SKIP

    def test_powered_camera_reachable_pass(self):
        poe = PoEResult(
            verdict=PoEVerdict.WARN,
            state=PoEState.POWERED,
            powered=True,
            power_w=15.4,
        )
        result = evaluate_poe_verdict(poe, camera_reachable=True)
        assert result.verdict == PoEVerdict.PASS

    def test_powered_camera_not_reachable_warn(self):
        poe = PoEResult(
            verdict=PoEVerdict.WARN,
            state=PoEState.POWERED,
            powered=True,
            power_w=15.4,
        )
        result = evaluate_poe_verdict(poe, camera_reachable=False)
        assert result.verdict == PoEVerdict.WARN

    def test_not_powered_warn(self):
        poe = PoEResult(
            verdict=PoEVerdict.WARN,
            state=PoEState.NOT_POWERED,
            powered=False,
            enabled=True,
        )
        result = evaluate_poe_verdict(poe, camera_reachable=False)
        assert result.verdict == PoEVerdict.WARN


class TestProbePoeStatus:
    def _make_adapter(self, poe_raw=None):
        adapter = MagicMock()
        adapter.get_poe_status.return_value = poe_raw or {}
        return adapter

    def test_port_not_poe(self):
        """Порт без PoE → SKIP."""
        port = PortInfo(index=1, name="1", supports_poe=False)
        adapter = self._make_adapter()
        result = probe_poe_status(adapter, MagicMock(), port)
        assert result.verdict == PoEVerdict.SKIP

    def test_adapter_no_poe_method(self):
        """Adapter без get_poe_status → SKIP."""
        port = PortInfo(index=1, name="1", supports_poe=True)
        adapter = MagicMock(spec=["get_mac_table", "get_counters"])
        result = probe_poe_status(adapter, MagicMock(), port)
        assert result.verdict == PoEVerdict.SKIP

    def test_adapter_empty_response(self):
        """Adapter вернул пустой ответ → WARN."""
        port = PortInfo(index=1, name="1", supports_poe=True)
        adapter = self._make_adapter(poe_raw={})
        result = probe_poe_status(adapter, MagicMock(), port)
        assert result.verdict == PoEVerdict.WARN

    def test_adapter_powered(self):
        """Adapter вернул powered статус."""
        port = PortInfo(index=1, name="1", supports_poe=True)
        adapter = self._make_adapter(poe_raw={"status": "ON", "power_w": "12.0"})
        result = probe_poe_status(adapter, MagicMock(), port)
        assert result.state == PoEState.POWERED
        assert result.powered is True
        assert result.power_w == 12.0

    def test_adapter_exception(self):
        """Adapter упал → WARN."""
        port = PortInfo(index=1, name="1", supports_poe=True)
        adapter = MagicMock()
        adapter.get_poe_status.side_effect = RuntimeError("timeout")
        result = probe_poe_status(adapter, MagicMock(), port)
        assert result.verdict == PoEVerdict.WARN
        assert any("timeout" in n for n in result.notes)


class TestWaitForCamera:
    @patch("switchlive.app.poe._check_tcp_reachable", return_value=True)
    def test_camera_immediately_reachable(self, _):
        reachable, waited = wait_for_camera(
            "192.168.1.50", timeout=10, check_interval=0.01
        )
        assert reachable is True
        assert waited < 5

    @patch("switchlive.app.poe._check_tcp_reachable", return_value=False)
    def test_camera_timeout(self, _):
        reachable, waited = wait_for_camera(
            "192.168.1.50", timeout=0.1, check_interval=0.05
        )
        assert reachable is False

    @patch("switchlive.app.poe._check_tcp_reachable", side_effect=[False, False, True])
    def test_camera_reachable_on_retry(self, _):
        reachable, waited = wait_for_camera(
            "192.168.1.50", timeout=30, check_interval=0.01
        )
        assert reachable is True


class TestPoEIndependenceFromEthernet:
    """PoE-вердикт независим от Ethernet — ключевое требование #11."""

    def test_poe_fail_ethernet_pass(self):
        """Порт может PASS Ethernet, но FAIL PoE."""
        poe = PoEResult(
            verdict=PoEVerdict.WARN,
            state=PoEState.FAULT,
            fault="short circuit",
        )
        result = evaluate_poe_verdict(poe, camera_reachable=False)
        assert result.verdict == PoEVerdict.FAIL
        # Ethernet verdict не затронут — он отдельно

    def test_poe_pass_ethernet_fail(self):
        """Порт может FAIL Ethernet, но PoE PASS."""
        poe = PoEResult(
            verdict=PoEVerdict.WARN,
            state=PoEState.POWERED,
            powered=True,
        )
        result = evaluate_poe_verdict(poe, camera_reachable=True)
        assert result.verdict == PoEVerdict.PASS
        # Ethernet verdict определяется отдельно (counters/link)
