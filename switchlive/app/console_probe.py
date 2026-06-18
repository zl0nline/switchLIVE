"""Lightweight serial console baudrate probe."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from switchlive.config import Config
from switchlive.core.errors import TransportError
from switchlive.transports.serial import SerialTransport, is_pyserial_available, list_serial_ports

DEFAULT_BAUDRATES = (9600, 115200)
PROMPT_MARKERS = (
    "login",
    "user name",
    "username",
    "password",
    "passwd",
    "press enter",
    "#",
    ">",
)


@dataclass(frozen=True)
class ConsoleProbeResult:
    """One serial port / baudrate probe result."""

    port: str
    baudrate: int
    opened: bool
    byte_count: int = 0
    readable: bool = False
    status: str = "silent"
    sample: str = ""
    raw_hex: str = ""
    error: str = ""


def baudrates_from_config(config: Config) -> tuple[int, ...]:
    """Return configured serial baudrates, falling back to common switch speeds."""
    serial = config.extra.get("serial")
    if not isinstance(serial, dict):
        return DEFAULT_BAUDRATES

    values = serial.get("default_baudrates")
    if not isinstance(values, list | tuple):
        return DEFAULT_BAUDRATES

    baudrates = []
    for value in values:
        try:
            baudrate = int(value)
        except (TypeError, ValueError):
            continue
        if baudrate > 0 and baudrate not in baudrates:
            baudrates.append(baudrate)

    return tuple(baudrates) or DEFAULT_BAUDRATES


def parse_baudrates(value: str) -> tuple[int, ...]:
    """Parse comma/space separated baudrate list from CLI."""
    baudrates = []
    for item in value.replace(",", " ").split():
        baudrate = int(item)
        if baudrate <= 0:
            raise ValueError(f"Invalid baudrate: {item}")
        if baudrate not in baudrates:
            baudrates.append(baudrate)
    if not baudrates:
        raise ValueError("No baudrates specified")
    return tuple(baudrates)


def probe_console(
    ports: Iterable[str] | None = None,
    baudrates: Iterable[int] = DEFAULT_BAUDRATES,
    timeout: float = 1.0,
    wakeup: bool = True,
) -> list[ConsoleProbeResult]:
    """Probe serial console output without attempting login or device detection."""
    if ports is None:
        serial_ports = list_serial_ports()
        if not serial_ports:
            if not is_pyserial_available():
                return [
                    ConsoleProbeResult(
                        port="",
                        baudrate=0,
                        opened=False,
                        status="error",
                        error="pyserial не установлен; запустите scripts/install-linux.sh",
                    )
                ]
            return [
                ConsoleProbeResult(
                    port="",
                    baudrate=0,
                    opened=False,
                    status="error",
                    error="COM-порты не найдены",
                )
            ]
        port_names = [port.name for port in serial_ports]
    else:
        port_names = list(ports)

    results: list[ConsoleProbeResult] = []
    for port in port_names:
        for baudrate in baudrates:
            results.append(_probe_one(port, int(baudrate), timeout=timeout, wakeup=wakeup))
    return results


def format_probe_report(results: list[ConsoleProbeResult]) -> str:
    """Format probe results for operator CLI output."""
    lines = ["Serial console probe:"]
    for result in results:
        if result.status == "error":
            target = result.port or "serial"
            lines.append(f"- {target}: ERROR — {result.error}")
            continue

        label = {
            "readable": "READABLE",
            "garbled": "GARBLED",
            "silent": "SILENT",
        }.get(result.status, result.status.upper())
        lines.append(f"- {result.port} @ {result.baudrate}: {label}, bytes={result.byte_count}")
        if result.sample:
            lines.append(f"  sample: {result.sample}")
        if result.raw_hex and result.status == "garbled":
            lines.append(f"  hex: {result.raw_hex}")
    return "\n".join(lines)


def write_probe_samples(results: list[ConsoleProbeResult], output_dir: str | Path) -> list[Path]:
    """Write non-empty probe samples to text files for later bug reports."""
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for result in results:
        if not result.byte_count:
            continue
        safe_port = result.port.replace("/", "_").replace("\\", "_").strip("_") or "serial"
        sample_path = path / f"console-probe-{safe_port}-{result.baudrate}.txt"
        sample_path.write_text(
            f"port={result.port}\nbaudrate={result.baudrate}\nstatus={result.status}\n"
            f"bytes={result.byte_count}\nhex={result.raw_hex}\n\n{result.sample}\n",
            encoding="utf-8",
        )
        written.append(sample_path)
    return written


def _probe_one(port: str, baudrate: int, timeout: float, wakeup: bool) -> ConsoleProbeResult:
    transport = SerialTransport(port=port, baudrate=baudrate, timeout=min(timeout, 0.2), idle_gap=0.2)
    try:
        transport.open()
        if wakeup:
            transport.write(b"\r\n")
        raw = transport.read_until_idle(timeout)
    except TransportError as e:
        return ConsoleProbeResult(
            port=port,
            baudrate=baudrate,
            opened=False,
            status="error",
            error=str(e),
        )
    finally:
        transport.close()

    status, readable, sample, raw_hex = _classify_raw_console(raw)
    return ConsoleProbeResult(
        port=port,
        baudrate=baudrate,
        opened=True,
        byte_count=len(raw),
        readable=readable,
        status=status,
        sample=sample,
        raw_hex=raw_hex,
    )


def _classify_raw_console(raw: bytes) -> tuple[str, bool, str, str]:
    if not raw:
        return "silent", False, "", ""

    text = raw.decode("utf-8", errors="replace")
    sample = _clean_sample(text)
    lowered = sample.lower()
    has_prompt_marker = any(marker in lowered for marker in PROMPT_MARKERS)
    printable = sum(1 for byte in raw if byte in (9, 10, 13) or 32 <= byte < 127)
    printable_ratio = printable / len(raw)
    replacement_ratio = sample.count("�") / max(len(sample), 1)
    readable = has_prompt_marker or (printable_ratio >= 0.70 and replacement_ratio <= 0.20)
    status = "readable" if readable else "garbled"
    return status, readable, sample, raw[:64].hex(" ")


def _clean_sample(text: str) -> str:
    compact = text.replace("\r", "\\r").replace("\n", "\\n")
    compact = "".join(char if char == "�" or char >= " " else "." for char in compact)
    return compact[:160]
