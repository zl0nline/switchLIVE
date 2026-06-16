"""Parsers for Eltex MES CLI output."""

from __future__ import annotations

import re

from switchlive.core.models import DeviceIdentity


def parse_show_version(output: str) -> DeviceIdentity:
    """Parse Eltex `show version` output."""
    model = (
        _extract_field(output, r"(?:Device|System)\s+(?:description|type)\s*:\s*(.+)")
        or _extract_field(output, r"Model\s*:\s*(.+)")
        or _extract_model(output)
    )
    serial = (
        _extract_field(output, r"Serial\s*(?:Number)?\s*:\s*(.+)")
        or _extract_field(output, r"System\s+serial\s+number\s*:\s*(.+)")
    )
    firmware = (
        _extract_field(output, r"(?:SW|Software)\s+version\s*:\s*(.+)")
        or _extract_field(output, r"Version\s*:\s*(.+)")
        or _extract_field(output, r"Active-image\s*:\s*(.+)")
    )

    return DeviceIdentity(
        vendor="Eltex",
        model=model or "unknown",
        serial=serial or "unknown",
        firmware=firmware or "unknown",
    )


def parse_mac_table(output: str) -> list[tuple[int, str]]:
    """Parse MAC address-table output into `(port_index, mac)` tuples."""
    entries = []
    for line in output.splitlines():
        mac_match = re.search(
            r"([0-9A-Fa-f]{2}(?:[:-][0-9A-Fa-f]{2}){5}|[0-9A-Fa-f]{4}(?:\.[0-9A-Fa-f]{4}){2})",
            line,
        )
        if not mac_match:
            continue
        port = _extract_port_index(line)
        if port is None:
            continue
        entries.append((port, _normalize_mac(mac_match.group(1))))
    return entries


def parse_counters(output: str) -> dict[str, int]:
    """Parse common interface counters."""
    counters = {}
    crc = _extract_number(output, r"(?:CRC|FCS)\s*(?:errors?)?\s*:?\s*(\d+)")
    if crc is not None:
        counters["crc"] = crc
    drops = _extract_number(output, r"(?:drops?|discarded)\s*:?\s*(\d+)")
    if drops is not None:
        counters["drops"] = drops
    collisions = _extract_number(output, r"collisions?\s*:?\s*(\d+)")
    if collisions is not None:
        counters["collisions"] = collisions
    return counters


def parse_transceiver(output: str) -> dict[str, str]:
    """Parse SFP/DOM-like output."""
    result = {}
    vendor = _extract_field(output, r"Vendor\s*(?:name)?\s*:?\s*(.+)")
    if vendor:
        result["vendor"] = vendor.strip()
    serial = _extract_field(output, r"Serial\s*(?:number)?\s*:?\s*(.+)")
    if serial:
        result["serial"] = serial.strip()

    rx = _extract_number(output, r"RX\s*(?:Power)?\s*:?\s*(-?[\d.]+)")
    if rx is not None:
        result["rx_power"] = str(rx)
    tx = _extract_number(output, r"TX\s*(?:Power)?\s*:?\s*(-?[\d.]+)")
    if tx is not None:
        result["tx_power"] = str(tx)
    temp = _extract_number(output, r"Temperature\s*:?\s*(-?[\d.]+)")
    if temp is not None:
        result["temperature"] = str(temp)
    return result


def _extract_field(text: str, pattern: str) -> str | None:
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None


def _extract_number(text: str, pattern: str) -> int | float | None:
    match = re.search(pattern, text, re.IGNORECASE)
    if not match:
        return None
    value = match.group(1)
    try:
        return int(value)
    except ValueError:
        try:
            return float(value)
        except ValueError:
            return None


def _extract_model(text: str) -> str | None:
    match = re.search(r"\b(MES2324FB|MES2324B)\b", text, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    return None


def _extract_port_index(text: str) -> int | None:
    match = re.search(
        r"(?:gi|te|gigabitethernet|tengigabitethernet)\s*1/0/(\d+)",
        text,
        re.IGNORECASE,
    )
    if match:
        return int(match.group(1))
    return None


def _normalize_mac(value: str) -> str:
    clean = value.replace("-", "").replace(":", "").replace(".", "").upper()
    return ":".join(clean[i : i + 2] for i in range(0, 12, 2))
