"""Парсеры CLI-вывода Eltex MES23xx.

Eltex использует Cisco-like CLI, поэтому паттерны отличаются от D-Link.
"""

from __future__ import annotations

import re

from switchlive.core.models import DeviceIdentity, PortInfo


def parse_show_version(output: str) -> DeviceIdentity:
    """Парсинг 'show version' для Eltex.

    Пример:
        Machine Description: MES2324B
        Serial Number: ELTX12345678
        Software Version: 4.0.13.1
    """
    model = _extract_field(output, r"Machine\s*(?:Type\s*)?Description\s*:\s*(.+)")
    if not model:
        model = _extract_field(output, r"(MES\d{4}\w*)")

    serial = _extract_field(output, r"Serial\s*Number\s*:\s*(.+)")
    firmware = _extract_field(output, r"Software\s*Version\s*:\s*(.+)")

    return DeviceIdentity(
        vendor="Eltex",
        model=model or "unknown",
        serial=serial or "unknown",
        firmware=firmware or "unknown",
    )


def parse_mac_table(output: str) -> list[tuple[int, str]]:
    """Парсинг 'show mac address-table' для Eltex.

    Пример:
        Vlan    Mac Address       Type    Ports
        1       00:1A:2B:3C:4D    Dyn     gi1/0/5
    """
    entries = []
    for match in re.finditer(
        r"\d+\s+([0-9A-Fa-f]{2}[:-][0-9A-Fa-f]{2}[:-][0-9A-Fa-f]{2}[:-]"
        r"[0-9A-Fa-f]{2}[:-][0-9A-Fa-f]{2}[:-][0-9A-Fa-f]{2})\s+\w+\s+"
        r"(gi\d+/\d+/\d+)",
        output,
        re.IGNORECASE,
    ):
        mac = match.group(1).replace("-", ":").upper()
        port_name = match.group(2)
        port_idx = _port_name_to_index(port_name)
        entries.append((port_idx, mac))

    return entries


def parse_interfaces_status(output: str) -> list[PortInfo]:
    """Парсинг 'show interfaces status' для Eltex.

    Пример:
        Port    Status   Speed    Duplex
        gi1/0/1 Up       1000     Full
    """
    ports = []
    for match in re.finditer(
        r"(gi\d+/\d+/\d+)\s+(\w+)\s+(\d+)\s+(\w+)",
        output,
        re.IGNORECASE,
    ):
        port_name = match.group(1)
        port_idx = _port_name_to_index(port_name)
        speed = int(match.group(3))

        ports.append(
            PortInfo(
                index=port_idx,
                name=port_name,
                cli_name=port_name,
                speed_mbps=speed,
                media="copper",
                connector="RJ45",
            )
        )

    return ports


def parse_counters(output: str) -> dict[str, int]:
    """Парсинг счётчиков интерфейса Eltex."""
    counters = {}
    crc = _extract_number(output, r"CRC\s*:?\s*(\d+)")
    if crc is not None:
        counters["crc"] = crc

    drops = _extract_number(output, r"(?:Drop|Discard)s?\s*:?\s*(\d+)")
    if drops is not None:
        counters["drops"] = drops

    collisions = _extract_number(output, r"Collision[s]?\s*:?\s*(\d+)")
    if collisions is not None:
        counters["collisions"] = collisions

    return counters


def parse_poe_status(output: str) -> dict[str, str]:
    """Парсинг 'show power inline' для Eltex."""
    result = {}
    status = _extract_field(output, r"(?:Admin|Oper)\s*Status\s*:\s*(\w+)")
    if status:
        result["status"] = status.upper()

    cls = _extract_field(output, r"Class\s*:\s*(\d+)")
    if cls:
        result["class"] = cls

    power = _extract_field(output, r"Power\s*(?:consumed|drawn)?\s*:?\s*([\d.]+)\s*W?")
    if power:
        result["power_w"] = power

    return result


def parse_transceiver(output: str) -> dict[str, str]:
    """Парсинг DOM данных SFP для Eltex."""
    result = {}
    vendor = _extract_field(output, r"Vendor\s*Name\s*:?\s*(.+)")
    if vendor:
        result["vendor"] = vendor.strip()

    serial = _extract_field(output, r"Vendor\s*Serial\s*(?:Number)?\s*:?\s*(.+)")
    if serial:
        result["serial"] = serial.strip()

    rx = _extract_number(output, r"RX\s*Power\s*:?\s*(-?[\d.]+)")
    if rx is not None:
        result["rx_power"] = str(rx)

    tx = _extract_number(output, r"TX\s*Power\s*:?\s*(-?[\d.]+)")
    if tx is not None:
        result["tx_power"] = str(tx)

    temp = _extract_number(output, r"Temperature\s*:?\s*(-?[\d.]+)")
    if temp is not None:
        result["temperature"] = str(temp)

    return result


# --- Вспомогательные ---

def _port_name_to_index(name: str) -> int:
    """gi1/0/5 → 5, gi1/0/25 → 25."""
    match = re.search(r"/(\d+)\s*$", name)
    if match:
        return int(match.group(1))
    return 0


def _extract_field(text: str, pattern: str) -> str | None:
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None


def _extract_number(text: str, pattern: str) -> int | float | None:
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        val = match.group(1)
        try:
            return int(val)
        except ValueError:
            try:
                return float(val)
            except ValueError:
                return None
    return None
