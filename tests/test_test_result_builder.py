"""Tests for converting walk-test runtime results into persisted reports."""

from __future__ import annotations

from datetime import datetime

from switchlive.app.test_result_builder import build_test_result
from switchlive.app.walk_test import PortTestResult
from switchlive.core.models import DeviceIdentity, LinkStatus, PortInfo, PortVerdict


def test_build_test_result_keeps_partial_ports_and_overall_warn():
    port = PortInfo(index=1, name="1", link_status=LinkStatus.UP, actual_speed=1000, duplex="Full")
    runtime = PortTestResult(
        port=port,
        verdict=PortVerdict.WARN,
        counters={"crc": 1, "drops": 0},
        iperf_throughput=94.0,
    )
    runtime.notes.append("partial")

    result = build_test_result(
        DeviceIdentity(vendor="D-Link", model="DGS-3000-10TC", serial="SN1"),
        [runtime],
        started_at=datetime(2026, 6, 17, 12, 0, 0),
        finished_at=datetime(2026, 6, 17, 12, 1, 0),
        comments="operator stopped",
    )

    assert result.overall_verdict == PortVerdict.WARN
    assert result.comments == "operator stopped"
    assert len(result.ports) == 1
    assert result.ports[0].link_up is True
    assert result.ports[0].speed_actual == 1000
    assert result.ports[0].crc_errors == 1
    assert result.ports[0].iperf_throughput_mbps == 94.0
    assert result.ports[0].notes == "partial"
