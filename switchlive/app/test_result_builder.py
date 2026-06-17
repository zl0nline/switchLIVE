"""Build persisted test results from walk-test runtime objects."""

from __future__ import annotations

from datetime import datetime

from switchlive.app.walk_test import PortTestResult
from switchlive.core.models import DeviceIdentity, LinkStatus, PortStatus, PortVerdict, TestResult


def build_test_result(
    device: DeviceIdentity,
    port_results: list[PortTestResult],
    *,
    started_at: datetime,
    finished_at: datetime | None = None,
    operator: str = "",
    comments: str = "",
) -> TestResult:
    """Convert walk-test results into the normalized persisted model."""
    result = TestResult(
        device=device,
        started_at=started_at,
        finished_at=finished_at or datetime.now(),
        operator=operator,
        comments=comments,
    )
    result.ports = [_port_status(item) for item in port_results]
    result.overall_verdict = _overall_verdict(result.ports)
    return result


def _port_status(result: PortTestResult) -> PortStatus:
    port = result.port
    status = PortStatus(
        port=port,
        link_up=port.link_status == LinkStatus.UP,
        speed_actual=port.actual_speed,
        duplex=port.duplex,
        crc_errors=result.counters.get("crc", port.crc_errors),
        drops=result.counters.get("drops", port.drops),
        flaps=port.flaps,
        iperf_throughput_mbps=result.iperf_throughput,
        verdict=result.verdict,
        notes="; ".join(result.notes),
    )

    sfp = result.sfp
    if sfp:
        status.sfp_vendor = str(getattr(sfp, "vendor", "") or "")
        status.sfp_serial = str(getattr(sfp, "serial", "") or "")
        status.sfp_rx_power = float(getattr(sfp, "rx_power_dbm", 0.0) or 0.0)
        status.sfp_tx_power = float(getattr(sfp, "tx_power_dbm", 0.0) or 0.0)
        status.sfp_temp = float(getattr(sfp, "temperature_c", 0.0) or 0.0)

    return status


def _overall_verdict(ports: list[PortStatus]) -> PortVerdict:
    if not ports:
        return PortVerdict.SKIP
    verdicts = {port.verdict for port in ports}
    if PortVerdict.FAIL in verdicts:
        return PortVerdict.FAIL
    if PortVerdict.WARN in verdicts:
        return PortVerdict.WARN
    if verdicts == {PortVerdict.PASS}:
        return PortVerdict.PASS
    return PortVerdict.WARN
