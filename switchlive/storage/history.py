"""SQLite history storage for completed switchLIVE test runs (#14)."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from switchlive.core.models import DeviceIdentity, PortInfo, PortStatus, PortVerdict, TestResult

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def init_db(db_path: str | Path) -> None:
    """Create SQLite database and schema if needed."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))


def save_test_result(db_path: str | Path, result: TestResult) -> int:
    """Persist a completed test result and return test_run id."""
    init_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        device_id = _upsert_device(conn, result.device)
        run_id = _insert_run(conn, device_id, result)
        for port in result.ports:
            _insert_port_result(conn, run_id, port)
        return run_id


def list_runs_by_serial(db_path: str | Path, serial: str) -> list[dict[str, Any]]:
    """Find historical runs by device serial number."""
    init_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT
                tr.id,
                d.serial,
                d.vendor,
                d.model,
                d.firmware,
                tr.started_at,
                tr.finished_at,
                tr.operator,
                tr.overall_verdict,
                tr.comments
            FROM test_runs tr
            JOIN devices d ON d.id = tr.device_id
            WHERE d.serial = ?
            ORDER BY tr.started_at DESC, tr.id DESC
            """,
            (serial,),
        ).fetchall()
        return [dict(row) for row in rows]


def load_test_result(db_path: str | Path, run_id: int) -> TestResult:
    """Load a TestResult from history for report regeneration."""
    init_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        run = conn.execute(
            """
            SELECT
                tr.*,
                d.vendor,
                d.model,
                d.serial,
                d.firmware
            FROM test_runs tr
            JOIN devices d ON d.id = tr.device_id
            WHERE tr.id = ?
            """,
            (run_id,),
        ).fetchone()
        if run is None:
            raise KeyError(f"test run not found: {run_id}")

        ports = conn.execute(
            """
            SELECT *
            FROM port_results
            WHERE run_id = ?
            ORDER BY port_index
            """,
            (run_id,),
        ).fetchall()

    result = TestResult(
        device=DeviceIdentity(
            vendor=run["vendor"],
            model=run["model"],
            serial=run["serial"],
            firmware=run["firmware"] or "unknown",
        ),
        operator=run["operator"] or "",
        overall_verdict=PortVerdict(run["overall_verdict"]),
        comments=run["comments"] or "",
    )
    result.started_at = _parse_datetime(run["started_at"])
    result.finished_at = _parse_datetime(run["finished_at"]) if run["finished_at"] else None
    result.ports = [_row_to_port_status(row) for row in ports]
    return result


def _upsert_device(conn: sqlite3.Connection, device: DeviceIdentity) -> int:
    now = _now_iso()
    serial = device.serial or "unknown"
    conn.execute(
        """
        INSERT INTO devices(serial, vendor, model, firmware, first_seen, last_seen)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(serial) DO UPDATE SET
            vendor = excluded.vendor,
            model = excluded.model,
            firmware = excluded.firmware,
            last_seen = excluded.last_seen
        """,
        (
            serial,
            device.vendor,
            device.model,
            device.firmware,
            now,
            now,
        ),
    )
    row = conn.execute("SELECT id FROM devices WHERE serial = ?", (serial,)).fetchone()
    return int(row["id"])


def _insert_run(conn: sqlite3.Connection, device_id: int, result: TestResult) -> int:
    cursor = conn.execute(
        """
        INSERT INTO test_runs(
            device_id,
            started_at,
            finished_at,
            operator,
            overall_verdict,
            comments
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            device_id,
            result.started_at.isoformat(),
            result.finished_at.isoformat() if result.finished_at else None,
            result.operator,
            result.overall_verdict.value,
            result.comments,
        ),
    )
    return int(cursor.lastrowid)


def _insert_port_result(conn: sqlite3.Connection, run_id: int, port: PortStatus) -> None:
    conn.execute(
        """
        INSERT INTO port_results(
            run_id,
            port_index,
            port_name,
            link_up,
            speed_actual,
            duplex,
            crc_errors,
            drops,
            flaps,
            iperf_throughput,
            poe_status,
            poe_class,
            sfp_vendor,
            sfp_serial,
            sfp_rx_power,
            sfp_tx_power,
            sfp_temp,
            verdict,
            notes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            port.port.index,
            port.port.name,
            int(port.link_up),
            port.speed_actual,
            port.duplex,
            port.crc_errors,
            port.drops,
            port.flaps,
            port.iperf_throughput_mbps,
            port.poe_status,
            port.poe_class,
            port.sfp_vendor,
            port.sfp_serial,
            port.sfp_rx_power,
            port.sfp_tx_power,
            port.sfp_temp,
            port.verdict.value,
            port.notes,
        ),
    )


def _row_to_port_status(row: sqlite3.Row) -> PortStatus:
    status = PortStatus(
        port=PortInfo(index=row["port_index"], name=row["port_name"]),
        link_up=bool(row["link_up"]),
        speed_actual=row["speed_actual"] or 0,
        duplex=row["duplex"] or "",
        crc_errors=row["crc_errors"] or 0,
        drops=row["drops"] or 0,
        flaps=row["flaps"] or 0,
        iperf_throughput_mbps=row["iperf_throughput"] or 0.0,
        poe_status=row["poe_status"] or "",
        poe_class=row["poe_class"] or "",
        sfp_vendor=row["sfp_vendor"] or "",
        sfp_serial=row["sfp_serial"] or "",
        sfp_rx_power=row["sfp_rx_power"] or 0.0,
        sfp_tx_power=row["sfp_tx_power"] or 0.0,
        sfp_temp=row["sfp_temp"] or 0.0,
        verdict=PortVerdict(row["verdict"]),
        notes=row["notes"] or "",
    )
    return status


def _now_iso() -> str:
    from datetime import datetime

    return datetime.now().isoformat(timespec="seconds")


def _parse_datetime(value: str):
    from datetime import datetime

    return datetime.fromisoformat(value)
