"""Tests for SQLite history and report exports (#14)."""

from __future__ import annotations

from datetime import datetime

from switchlive.core.models import (
    DeviceIdentity,
    PortInfo,
    PortStatus,
    PortVerdict,
)
from switchlive.core.models import (
    TestResult as SwitchTestResult,
)
from switchlive.reports.generator import export_csv, export_html, render_csv, render_html
from switchlive.storage.history import list_runs_by_serial, load_test_result, save_test_result


def _sample_result() -> SwitchTestResult:
    result = SwitchTestResult(
        device=DeviceIdentity(
            vendor="D-Link",
            model="DGS-3420/SC",
            serial="SN123",
            firmware="1.0",
        ),
        started_at=datetime(2026, 6, 16, 12, 0, 0),
        finished_at=datetime(2026, 6, 16, 12, 5, 0),
        operator="operator",
        overall_verdict=PortVerdict.WARN,
        comments="field test",
    )
    result.ports = [
        PortStatus(
            port=PortInfo(index=1, name="1"),
            link_up=True,
            speed_actual=1000,
            crc_errors=0,
            drops=0,
            iperf_throughput_mbps=940.5,
            poe_status="PASS",
            poe_class="3",
            verdict=PortVerdict.PASS,
            notes="ok",
        ),
        PortStatus(
            port=PortInfo(index=25, name="25"),
            link_up=True,
            speed_actual=10000,
            sfp_vendor="Finisar",
            sfp_serial="SFP123",
            sfp_rx_power=-3.5,
            sfp_tx_power=-2.1,
            sfp_temp=35.2,
            verdict=PortVerdict.WARN,
            notes="DOM warning",
        ),
    ]
    return result


class TestHistoryStorage:
    def test_save_and_find_by_serial(self, tmp_path):
        db_path = tmp_path / "history.sqlite"
        run_id = save_test_result(db_path, _sample_result())

        rows = list_runs_by_serial(db_path, "SN123")

        assert run_id > 0
        assert len(rows) == 1
        assert rows[0]["serial"] == "SN123"
        assert rows[0]["model"] == "DGS-3420/SC"

    def test_load_test_result(self, tmp_path):
        db_path = tmp_path / "history.sqlite"
        run_id = save_test_result(db_path, _sample_result())

        loaded = load_test_result(db_path, run_id)

        assert loaded.device.serial == "SN123"
        assert loaded.overall_verdict == PortVerdict.WARN
        assert len(loaded.ports) == 2
        assert loaded.ports[1].sfp_vendor == "Finisar"

    def test_repeated_device_returns_are_grouped_by_serial(self, tmp_path):
        db_path = tmp_path / "history.sqlite"
        save_test_result(db_path, _sample_result())
        save_test_result(db_path, _sample_result())

        rows = list_runs_by_serial(db_path, "SN123")

        assert len(rows) == 2


class TestReports:
    def test_render_html_contains_device_and_ports(self):
        html = render_html(_sample_result())

        assert "DGS-3420/SC" in html
        assert "SN123" in html
        assert "Finisar" in html
        assert "PASS" in html

    def test_render_csv_contains_rows(self):
        csv_text = render_csv(_sample_result())

        assert "serial,vendor,model" in csv_text
        assert "SN123,D-Link,DGS-3420/SC" in csv_text
        assert "SFP123" in csv_text

    def test_export_files(self, tmp_path):
        result = _sample_result()
        html_path = export_html(result, tmp_path / "report.html")
        csv_path = export_csv(result, tmp_path / "report.csv")

        assert html_path.exists()
        assert csv_path.exists()
        assert "switchLIVE report" in html_path.read_text(encoding="utf-8")
