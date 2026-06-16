"""Tests for finalization flow (#15)."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

from switchlive.app.finalize import (
    FinalizeConfig,
    FinalizeStatus,
    finalize_after_test,
)
from switchlive.core.models import (
    DeviceIdentity,
    PortInfo,
    PortStatus,
    PortVerdict,
)
from switchlive.core.models import (
    TestResult as SwitchTestResult,
)


def _sample_result() -> SwitchTestResult:
    result = SwitchTestResult(
        device=DeviceIdentity(vendor="D-Link", model="DES-1228", serial="SN123"),
        started_at=datetime(2026, 6, 16, 12, 0, 0),
        finished_at=datetime(2026, 6, 16, 12, 10, 0),
        operator="operator",
        overall_verdict=PortVerdict.PASS,
    )
    result.ports = [
        PortStatus(
            port=PortInfo(index=1, name="1"),
            link_up=True,
            speed_actual=1000,
            verdict=PortVerdict.PASS,
        )
    ]
    return result


def _adapter(supports_reset=True, factory_reset_cmd="reset config"):
    profile = MagicMock()
    profile.supports_reset = supports_reset
    profile.factory_reset_cmd = factory_reset_cmd
    adapter = MagicMock()
    adapter.profile = profile
    adapter.factory_reset.return_value = None
    return adapter


class TestFinalizeAfterTest:
    def test_reports_and_history_survive_reset(self, tmp_path):
        adapter = _adapter()
        session = MagicMock()
        result = finalize_after_test(
            adapter,
            session,
            _sample_result(),
            FinalizeConfig(
                factory_reset=True,
                report_dir=tmp_path / "reports",
                db_path=tmp_path / "history.sqlite",
            ),
        )

        assert result.status == FinalizeStatus.DONE
        assert result.history_run_id is not None
        assert result.html_report.exists()
        assert result.csv_report.exists()
        adapter.factory_reset.assert_called_once_with(session)

    def test_reset_skipped_without_explicit_config(self, tmp_path):
        adapter = _adapter()
        result = finalize_after_test(
            adapter,
            MagicMock(),
            _sample_result(),
            FinalizeConfig(factory_reset=False, report_dir=tmp_path),
        )

        assert result.status == FinalizeStatus.RESET_SKIPPED
        assert result.reset_attempted is False
        adapter.factory_reset.assert_not_called()

    def test_unsupported_reset_is_not_attempted(self, tmp_path):
        adapter = _adapter(supports_reset=False)
        result = finalize_after_test(
            adapter,
            MagicMock(),
            _sample_result(),
            FinalizeConfig(factory_reset=True, report_dir=tmp_path),
        )

        assert result.status == FinalizeStatus.UNSUPPORTED
        assert result.reset_attempted is False
        adapter.factory_reset.assert_not_called()

    def test_reset_failure_is_reported(self, tmp_path):
        adapter = _adapter()
        adapter.factory_reset.side_effect = RuntimeError("timeout")
        result = finalize_after_test(
            adapter,
            MagicMock(),
            _sample_result(),
            FinalizeConfig(factory_reset=True, report_dir=tmp_path),
        )

        assert result.status == FinalizeStatus.RESET_FAIL
        assert result.reset_attempted is True
        assert result.reset_ok is False
        assert result.html_report.exists()
        assert "timeout" in result.errors[0]
