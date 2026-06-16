"""HTML and CSV report generation for switchLIVE test results (#14)."""

from __future__ import annotations

import csv
import html
from io import StringIO
from pathlib import Path

from switchlive.core.models import PortStatus, PortVerdict, TestResult


def export_html(result: TestResult, output_path: str | Path) -> Path:
    """Write a human-readable HTML report and return its path."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_html(result), encoding="utf-8")
    return path


def export_csv(result: TestResult, output_path: str | Path) -> Path:
    """Write a spreadsheet-friendly CSV report and return its path."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_csv(result), encoding="utf-8", newline="")
    return path


def render_html(result: TestResult) -> str:
    device = result.device
    rows = "\n".join(_render_port_row(port) for port in result.ports)
    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <title>switchLIVE report - {_e(device.serial)}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 32px; color: #1f2937; }}
    h1 {{ margin-bottom: 4px; }}
    .meta {{ color: #4b5563; margin-bottom: 24px; }}
    .summary {{ display: flex; gap: 12px; margin: 18px 0; }}
    .pill {{ padding: 6px 10px; border-radius: 6px; background: #f3f4f6; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
    th, td {{ border-bottom: 1px solid #e5e7eb; padding: 8px; text-align: left; vertical-align: top; }}
    th {{ background: #f9fafb; }}
    .PASS {{ color: #047857; font-weight: 700; }}
    .PASS_WITH_WARNINGS {{ color: #b45309; font-weight: 700; }}
    .FAIL {{ color: #b91c1c; font-weight: 700; }}
    .SKIP {{ color: #6b7280; font-weight: 700; }}
  </style>
</head>
<body>
  <h1>switchLIVE report</h1>
  <div class="meta">
    {_e(device.vendor)} {_e(device.model)} · serial {_e(device.serial)} · firmware {_e(device.firmware)}
  </div>
  <div class="summary">
    <div class="pill">Operator: {_e(result.operator)}</div>
    <div class="pill">Started: {_e(result.started_at.isoformat(timespec="seconds"))}</div>
    <div class="pill">Finished: {_e(result.finished_at.isoformat(timespec="seconds") if result.finished_at else "")}</div>
    <div class="pill">Overall: <span class="{result.overall_verdict.value}">{_e(result.overall_verdict.value)}</span></div>
  </div>
  <p>{_e(result.comments)}</p>
  <table>
    <thead>
      <tr>
        <th>Port</th>
        <th>Verdict</th>
        <th>Ethernet</th>
        <th>PoE</th>
        <th>SFP</th>
        <th>Traffic</th>
        <th>Notes</th>
      </tr>
    </thead>
    <tbody>
      {rows}
    </tbody>
  </table>
</body>
</html>
"""


def render_csv(result: TestResult) -> str:
    """Render report as CSV text."""
    out = StringIO()
    writer = csv.writer(out)
    writer.writerow(
        [
            "serial",
            "vendor",
            "model",
            "firmware",
            "operator",
            "started_at",
            "finished_at",
            "overall_verdict",
            "port_index",
            "port_name",
            "port_verdict",
            "link_up",
            "speed_actual",
            "crc_errors",
            "drops",
            "iperf_mbps",
            "poe_status",
            "poe_class",
            "sfp_vendor",
            "sfp_serial",
            "sfp_rx_power",
            "sfp_tx_power",
            "sfp_temp",
            "notes",
        ]
    )
    for port in result.ports:
        writer.writerow(_csv_row(result, port))
    return out.getvalue()


def _render_port_row(port: PortStatus) -> str:
    ethernet = (
        f"link={'up' if port.link_up else 'down'}, "
        f"speed={port.speed_actual}, crc={port.crc_errors}, drops={port.drops}"
    )
    poe = f"{port.poe_status} class={port.poe_class}".strip()
    sfp = (
        f"{port.sfp_vendor} {port.sfp_serial} "
        f"rx={port.sfp_rx_power} tx={port.sfp_tx_power} temp={port.sfp_temp}"
    ).strip()
    traffic = f"{port.iperf_throughput_mbps:.2f} Mbps"
    return f"""<tr>
  <td>{_e(port.port.name)}</td>
  <td class="{port.verdict.value}">{_e(port.verdict.value)}</td>
  <td>{_e(ethernet)}</td>
  <td>{_e(poe)}</td>
  <td>{_e(sfp)}</td>
  <td>{_e(traffic)}</td>
  <td>{_e(port.notes)}</td>
</tr>"""


def _csv_row(result: TestResult, port: PortStatus) -> list:
    device = result.device
    return [
        device.serial,
        device.vendor,
        device.model,
        device.firmware,
        result.operator,
        result.started_at.isoformat(timespec="seconds"),
        result.finished_at.isoformat(timespec="seconds") if result.finished_at else "",
        result.overall_verdict.value,
        port.port.index,
        port.port.name,
        port.verdict.value,
        int(port.link_up),
        port.speed_actual,
        port.crc_errors,
        port.drops,
        port.iperf_throughput_mbps,
        port.poe_status,
        port.poe_class,
        port.sfp_vendor,
        port.sfp_serial,
        port.sfp_rx_power,
        port.sfp_tx_power,
        port.sfp_temp,
        port.notes,
    ]


def _e(value) -> str:
    return html.escape(str(value), quote=True)
