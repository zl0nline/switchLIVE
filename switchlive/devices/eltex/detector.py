"""Eltex MES detector."""

from __future__ import annotations

import logging
import re

from switchlive.core.models import DeviceIdentity
from switchlive.devices.base import DeviceDetector, DeviceSession
from switchlive.devices.eltex.parsers import parse_show_inventory, parse_show_version
from switchlive.devices.eltex.profiles import get_profile_for_model
from switchlive.devices.registry import register_detector

log = logging.getLogger(__name__)

# Patterns to detect Eltex in show version output
_ELTEX_TEXT_PATTERNS = [
    re.compile(r"Eltex", re.IGNORECASE),
    re.compile(r"\bMES\d{2,4}", re.IGNORECASE),        # MES23, MES2324, MES3300, etc.
    re.compile(r"\bmes\d+.*\.ros", re.IGNORECASE),      # mes3300-4020-R3.ros
]


@register_detector("eltex")
class EltexDetector(DeviceDetector):
    """Detector for Eltex MES switches."""

    def can_detect(self, session: DeviceSession) -> bool:
        try:
            result = session.run_command("show version", timeout=5.0)
            if not result.success:
                return False
            text = result.output
            return any(p.search(text) for p in _ELTEX_TEXT_PATTERNS)
        except Exception:
            return False

    def identify(self, session: DeviceSession) -> DeviceIdentity:
        # Try show inventory first — has real model + serial number
        try:
            inv_result = session.run_command("show inventory", timeout=10.0)
            if inv_result.success and "PID:" in inv_result.output:
                identity = parse_show_inventory(inv_result.output)
                if identity.model != "unknown":
                    # Enrich with firmware from show version
                    ver_result = session.run_command("show version", timeout=10.0)
                    if ver_result.success:
                        ver_identity = parse_show_version(ver_result.output)
                        if ver_identity.firmware != "unknown":
                            identity.firmware = ver_identity.firmware
                    log.info(
                        "Identified via show inventory: model=%s serial=%s",
                        identity.model,
                        identity.serial,
                    )
                    if get_profile_for_model(identity.model) is None:
                        log.info("No profile for Eltex model: %s", identity.model)
                    return identity
        except Exception as e:
            log.debug("show inventory failed: %s", e)

        # Fallback to show version only
        result = session.run_command("show version", timeout=10.0)
        identity = parse_show_version(result.output)
        if identity.model == "unknown":
            log.warning("Eltex detected but model unknown")
        elif get_profile_for_model(identity.model) is None:
            log.info("No profile for Eltex model: %s", identity.model)
        return identity
