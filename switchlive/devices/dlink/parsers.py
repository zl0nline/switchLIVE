"""Парсеры CLI-вывода D-Link коммутаторов.

Каждый парсер принимает сырой текст из CLI и возвращает нормализованные данные.
Не выполняют команд — только парсинг.
"""

from __future__ import annotations

import re

from switchlive.core.models import AdminStatus, DeviceIdentity, LinkStatus, PortInfo


def parse_show_switch(output: str) -> DeviceIdentity:
    """Парсинг 'show switch' для D-Link.

    Пример вывода:
        Device Type: DES-1228
        Hardware Version: A1
    Firmware Version: 2.00.B01
        Serial Number: PZA00AB00001

    Возвращает DeviceIdentity с vendor=D-Link.
    """
    model = _extract_field(output, r"Device\s*Type\s*:\s*(.+)")
    firmware = _extract_field(output, r"Firmware\s*Version\s*:\s*(.+)")
    serial = _extract_field(output, r"Serial\s*Number\s*:\s*(.+)")
    _extract_field(output, r"Hardware\s*Version\s*:\s*(.+)")

    return DeviceIdentity(
        vendor="D-Link",
        model=model or "unknown",
        serial=serial or "unknown",
        firmware=firmware or "unknown",
    )


def parse_show_ports(output: str) -> list[PortInfo]:
    """Парсинг 'show ports' для D-Link.

    Пример вывода:
        Port   State/Link  Speed   Duplex
        1      Enabled/Up  100M    Full
        2      Enabled/Up  1G      Full
        25     Disabled    --      --

    Возвращает список PortInfo.
    """
    ports = []
    for match in re.finditer(
        r"(\d+)\s+(\w+)/(\w+)\s+(\d+[MG]?)\s+(\w+)", output, re.IGNORECASE
    ):
        idx = int(match.group(1))
        admin_str = match.group(2).lower()
        link_str = match.group(3).lower()
        speed_str = match.group(4).upper()
        duplex = match.group(5)

        speed_mbps = _parse_speed(speed_str)
        admin_status = AdminStatus.ENABLED if admin_str == "enabled" else AdminStatus.DISABLED
        link_status = LinkStatus.UP if link_str == "up" else LinkStatus.DOWN
        ports.append(
            PortInfo(
                index=idx,
                name=str(idx),
                speed_mbps=speed_mbps,
                media="copper",
                connector="RJ45",
                admin_status=admin_status,
                link_status=link_status,
                actual_speed=speed_mbps if link_status == LinkStatus.UP else 0,
                duplex=duplex,
            )
        )

    return ports


def parse_mac_table(output: str) -> list[tuple[int, str]]:
    """Парсинг 'show fdb' для D-Link.

    Пример:
        VLAN    MAC Address     Port
        1       00-1A-2B-3C-4D  5
        1       00-50-BA-12-34  1

    Возвращает [(port_index, mac_address), ...].
    """
    entries = []
    seen: set[tuple[int, str]] = set()
    for match in re.finditer(
        r"\d+\s+([0-9A-Fa-f]{2}[:-][0-9A-Fa-f]{2}[:-][0-9A-Fa-f]{2}[:-][0-9A-Fa-f]{2}[:-][0-9A-Fa-f]{2}[:-][0-9A-Fa-f]{2})\s+(\d+)",
        output,
        re.IGNORECASE,
    ):
        mac = match.group(1).replace("-", ":").upper()
        port = int(match.group(2))
        item = (port, mac)
        if item not in seen:
            entries.append(item)
            seen.add(item)

    for line in output.splitlines():
        mac_match = re.search(
            r"([0-9A-Fa-f]{2}[:-][0-9A-Fa-f]{2}[:-][0-9A-Fa-f]{2}[:-][0-9A-Fa-f]{2}[:-][0-9A-Fa-f]{2}[:-][0-9A-Fa-f]{2})",
            line,
        )
        if not mac_match:
            continue
        port = _extract_port_after_mac(line[mac_match.end():])
        if port is None:
            continue
        mac = mac_match.group(1).replace("-", ":").upper()
        item = (port, mac)
        if item not in seen:
            entries.append(item)
            seen.add(item)

    return entries


def parse_counters(output: str) -> dict[str, int]:
    """Парсинг счётчиков порта для D-Link.

    Ищет CRC, dropped, collisions и т.д.
    """
    counters = {}
    crc = _extract_number(output, r"CRC\s*(?:Error[s]?)?\s*:?\s*(\d+)")
    if crc is not None:
        counters["crc"] = crc

    drops = _extract_number(output, r"Drop[s]?\s*:?\s*(\d+)")
    if drops is not None:
        counters["drops"] = drops

    collisions = _extract_number(output, r"Collision[s]?\s*:?\s*(\d+)")
    if collisions is not None:
        counters["collisions"] = collisions

    return counters


def parse_poe_status(output: str) -> dict[str, str]:
    """Парсинг PoE статуса порта.

    Возвращает dict: status, class, power_w.
    """
    result = {}
    status = _extract_field(output, r"(?:PoE\s*)?Status\s*:\s*(\w+)")
    if status:
        result["status"] = status

    cls = _extract_field(output, r"Class\s*:\s*(\d+)")
    if cls:
        result["class"] = cls

    power = _extract_field(output, r"Power\s*:\s*([\d.]+)\s*W?")
    if power:
        result["power_w"] = power

    return result


def parse_transceiver(output: str) -> dict[str, str]:
    """Парсинг 'show transceiver' для SFP/DOM данных."""
    result = {}
    vendor = _extract_field(output, r"Vendor\s*:\s*(.+)")
    if vendor:
        result["vendor"] = vendor.strip()

    serial = _extract_field(output, r"Serial\s*(?:Number)?\s*:\s*(.+)")
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


def _parse_speed(speed_str: str) -> int:
    """Парсинг строки скорости: '100M' → 100, '1G' → 1000."""
    speed_str = speed_str.upper().strip()
    if speed_str.endswith("G"):
        return int(float(speed_str[:-1]) * 1000)
    if speed_str.endswith("M"):
        return int(speed_str[:-1])
    try:
        return int(speed_str)
    except ValueError:
        return 0


def _extract_port_after_mac(text: str) -> int | None:
    for token in re.split(r"\s+", text.strip()):
        cleaned = token.strip("[](),")
        if not cleaned:
            continue
        if cleaned.isdigit():
            return int(cleaned)
        slash_match = re.search(r"(?:\d+/)*(\d+)$", cleaned)
        if slash_match:
            return int(slash_match.group(1))
    return None
