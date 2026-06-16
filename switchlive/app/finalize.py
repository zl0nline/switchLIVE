"""Finalization flow: reports, history, factory reset and reload (#15)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from switchlive.core.models import TestResult
from switchlive.devices.base import DeviceAdapter, DeviceSession
from switchlive.reports.generator import export_csv, export_html
from switchlive.storage.history import save_test_result


class FinalizeStatus(str, Enum):
    """Post-test finalization outcome."""

    DONE = "DONE"
    SKIPPED = "SKIPPED"
    RESET_SKIPPED = "RESET_SKIPPED"
    RESET_FAIL = "RESET_FAIL"
    REPORT_FAIL = "REPORT_FAIL"
    UNSUPPORTED = "UNSUPPORTED"


@dataclass
class FinalizeConfig:
    """Explicit finalization settings.

    Factory reset is never implicit: set factory_reset=True only after an
    operator confirmation or config policy decision.
    """

    factory_reset: bool = False
    report_dir: str | Path | None = None
    db_path: str | Path | None = None


@dataclass
class FinalizeResult:
    status: FinalizeStatus = FinalizeStatus.SKIPPED
    history_run_id: int | None = None
    html_report: Path | None = None
    csv_report: Path | None = None
    reset_attempted: bool = False
    reset_ok: bool = False
    errors: list[str] = field(default_factory=list)


def finalize_after_test(
    adapter: DeviceAdapter,
    session: DeviceSession,
    test_result: TestResult,
    config: FinalizeConfig,
) -> FinalizeResult:
    """Persist artifacts and optionally reset/reload the device."""
    result = FinalizeResult(status=FinalizeStatus.DONE)

    try:
        _persist_artifacts(test_result, config, result)
    except Exception as e:
        result.status = FinalizeStatus.REPORT_FAIL
        result.errors.append(f"report/history failed: {e}")
        return result

    if not config.factory_reset:
        result.status = FinalizeStatus.RESET_SKIPPED
        return result

    if not _supports_factory_reset(adapter):
        result.status = FinalizeStatus.UNSUPPORTED
        result.errors.append("factory reset unsupported by adapter/profile")
        return result

    result.reset_attempted = True
    try:
        adapter.factory_reset(session)
    except Exception as e:
        result.status = FinalizeStatus.RESET_FAIL
        result.errors.append(f"factory reset failed: {e}")
        return result

    result.reset_ok = True
    result.status = FinalizeStatus.DONE
    return result


def _persist_artifacts(
    test_result: TestResult,
    config: FinalizeConfig,
    result: FinalizeResult,
) -> None:
    if config.db_path:
        result.history_run_id = save_test_result(config.db_path, test_result)

    if config.report_dir:
        report_dir = Path(config.report_dir)
        stem = _report_stem(test_result)
        result.html_report = export_html(test_result, report_dir / f"{stem}.html")
        result.csv_report = export_csv(test_result, report_dir / f"{stem}.csv")


def _supports_factory_reset(adapter: DeviceAdapter) -> bool:
    profile = getattr(adapter, "profile", None)
    if profile is None:
        return False
    if not getattr(profile, "supports_reset", False):
        return False
    return bool(getattr(profile, "factory_reset_cmd", ""))


def _report_stem(test_result: TestResult) -> str:
    serial = _safe_part(test_result.device.serial or "unknown")
    started = test_result.started_at.strftime("%Y%m%d-%H%M%S")
    return f"{serial}-{started}"


def _safe_part(value: str) -> str:
    allowed = []
    for char in value:
        if char.isalnum() or char in ("-", "_"):
            allowed.append(char)
        else:
            allowed.append("_")
    return "".join(allowed).strip("_") or "unknown"
