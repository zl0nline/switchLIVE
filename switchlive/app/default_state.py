"""Pre-test factory-default state checks."""

from __future__ import annotations

from dataclasses import dataclass, field

from switchlive.devices.base import DeviceAdapter, DeviceSession
from switchlive.devices.dlink.adapter import DLinkAdapter
from switchlive.devices.dlink.parsers import parse_show_switch_default_state


@dataclass(frozen=True)
class DefaultStateCheck:
    """Result of a best-effort factory-default check."""

    supported: bool
    is_default: bool
    reasons: list[str] = field(default_factory=list)
    evidence: dict[str, str] = field(default_factory=dict)


def check_default_state(adapter: DeviceAdapter, session: DeviceSession) -> DefaultStateCheck:
    """Check whether device looks clean enough for a port test."""
    if isinstance(adapter, DLinkAdapter):
        result = session.run_command(adapter.profile.show_version_cmd)
        is_default, reasons, evidence = parse_show_switch_default_state(result.output)
        return DefaultStateCheck(
            supported=True,
            is_default=is_default,
            reasons=reasons,
            evidence=evidence,
        )

    return DefaultStateCheck(supported=False, is_default=True)
