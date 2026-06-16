"""SFP/SFP+ probe — normalized module and DOM metrics (#12)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from switchlive.core.models import PortInfo, PortType
from switchlive.devices.base import DeviceAdapter, DeviceSession


class SfpVerdict(str, Enum):
    """Independent SFP test verdict."""

    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"
    SKIP = "SKIP"


@dataclass
class SfpResult:
    """Normalized SFP/SFP+ module state and DOM metrics."""

    verdict: SfpVerdict = SfpVerdict.WARN
    supported: bool = True
    present: bool = False
    dom_supported: bool = False
    vendor: str = ""
    serial: str = ""
    rx_power_dbm: float | None = None
    tx_power_dbm: float | None = None
    temperature_c: float | None = None
    notes: list[str] = field(default_factory=list)


def probe_sfp_status(
    adapter: DeviceAdapter,
    session: DeviceSession,
    port: PortInfo,
) -> SfpResult:
    """Read and normalize SFP module metadata and DOM metrics."""
    if port.type not in (PortType.SFP, PortType.SFP_PLUS, PortType.COMBO):
        return SfpResult(
            verdict=SfpVerdict.SKIP,
            supported=False,
            notes=["Порт не является SFP/SFP+"],
        )

    if not hasattr(adapter, "get_transceiver"):
        return SfpResult(
            verdict=SfpVerdict.WARN,
            supported=False,
            notes=["Adapter не поддерживает чтение SFP/DOM"],
        )

    try:
        raw = adapter.get_transceiver(session, port)
    except Exception as e:
        return SfpResult(
            verdict=SfpVerdict.WARN,
            notes=[f"SFP query failed: {e}"],
        )

    if not raw:
        return SfpResult(
            verdict=SfpVerdict.WARN,
            notes=["SFP/DOM: пустой ответ от adapter"],
        )

    return evaluate_sfp_result(_normalize_sfp(raw))


def evaluate_sfp_result(sfp: SfpResult) -> SfpResult:
    """Evaluate normalized SFP data."""
    if sfp.verdict == SfpVerdict.SKIP:
        return sfp

    if not sfp.present:
        sfp.verdict = SfpVerdict.WARN
        sfp.notes.append("SFP модуль не обнаружен или metadata отсутствует")
        return sfp

    if not sfp.dom_supported:
        sfp.verdict = SfpVerdict.WARN
        sfp.notes.append("DOM metrics недоступны")
        return sfp

    sfp.verdict = SfpVerdict.PASS
    sfp.notes.append("SFP DOM metrics доступны")
    return sfp


def _normalize_sfp(raw: dict) -> SfpResult:
    """Normalize vendor-specific transceiver output."""
    result = SfpResult()

    vendor = str(raw.get("vendor", raw.get("vendor_name", ""))).strip()
    serial = str(raw.get("serial", raw.get("serial_number", ""))).strip()
    result.vendor = vendor
    result.serial = serial
    result.present = bool(vendor or serial)

    result.rx_power_dbm = _optional_float(
        raw.get("rx_power", raw.get("rx_power_dbm"))
    )
    result.tx_power_dbm = _optional_float(
        raw.get("tx_power", raw.get("tx_power_dbm"))
    )
    result.temperature_c = _optional_float(
        raw.get("temperature", raw.get("temperature_c"))
    )
    result.dom_supported = any(
        value is not None
        for value in (
            result.rx_power_dbm,
            result.tx_power_dbm,
            result.temperature_c,
        )
    )

    return result


def _optional_float(value) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
