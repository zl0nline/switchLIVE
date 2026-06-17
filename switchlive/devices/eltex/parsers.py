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


def parse_show_inventory(output: str) -> DeviceIdentity:
    """Parse Eltex `show inventory` output.

    Example output:
        NAME: "1"   DESCR: "28-port 1G/10G Managed Switch"
        PID: MES2324 AC   VID: 0   SN: ES2A015942

    This is more reliable than show version for model/serial, because
    firmware images are shared across model families (e.g. mes3300*.ros
    runs on both MES2324 and MES3300 hardware).
    """
    model = _extract_field(output, r"PID:\s*(\S+(?:\s+\S+)*?)\s+VID:")
    if not model:
        model = _extract_field(output, r"PID:\s*(.+)")
    # Normalize: extract full model identifier from PID
    # PID can be: "MES2324 AC", "MES2324FB", "MES3300-24T"
    if model:
        match = re.match(r"(MES\d{2,4}[A-Z]*)", model, re.IGNORECASE)
        if match:
            model = match.group(1).upper()

    serial = _extract_field(output, r"SN:\s*(\S+)")
    if not serial:
        serial = _extract_field(output, r"Serial\s*(?:Number)?\s*:\s*(.+)")

    return DeviceIdentity(
        vendor="Eltex",
        model=model or "unknown",
        serial=serial or "unknown",
        firmware="unknown",  # show inventory does not include firmware
    )


def parse_show_system(output: str) -> DeviceIdentity:
    """Parse Eltex `show system` output as fallback for model."""
    model = _extract_field(output, r"System Description\s*:\s*(.+)")
    if model:
        match = re.search(r"(MES\d{2,4})", model, re.IGNORECASE)
        if match:
            model = match.group(1).upper()

    return DeviceIdentity(
        vendor="Eltex",
        model=model or "unknown",
        serial="unknown",
        firmware="unknown",
    )


def parse_show_interfaces_status(output: str) -> dict[str, dict]:
    """Parse Eltex `show interfaces status` output.

    Returns dict keyed by CLI port name (e.g. 'gi1/0/1') with:
        link_state: 'up' | 'down'
        speed_mbps: int
        duplex: str

    Example line:
        gi1/0/23 1G-Copper    Full    100   Enabled  Off  Up     00,00:02:09
    """
    result = {}
    for line in output.splitlines():
        # Match port lines: gi1/0/N or te1/0/N
        match = re.match(
            r"^\s*((?:gi|te)\d+/\d+/\d+)\s+\S+\s+"
            r"(\S+)?\s+(\S+)?\s+.*?\b(Up|Down)\b",
            line,
            re.IGNORECASE,
        )
        if not match:
            continue
        port_name = match.group(1).lower()
        duplex = match.group(2) or ""
        speed_str = match.group(3) or ""
        link_state = match.group(4).lower()

        speed_mbps = 0
        if speed_str.isdigit():
            speed_mbps = int(speed_str)
        elif "1000" in speed_str:
            speed_mbps = 1000
        elif "10G" in speed_str or "10000" in speed_str:
            speed_mbps = 10000

        result[port_name] = {
            "link_state": link_state,
            "speed_mbps": speed_mbps,
            "duplex": duplex,
        }
    return result


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
    # Exact known models first (with optional suffix letters)
    match = re.search(r"\b(MES\d{2,4}[A-Z]*)\b", text, re.IGNORECASE)
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
