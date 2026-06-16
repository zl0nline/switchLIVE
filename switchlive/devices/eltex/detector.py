"""Eltex MES detector."""

from __future__ import annotations

import logging

from switchlive.core.models import DeviceIdentity
from switchlive.devices.base import DeviceDetector, DeviceSession
from switchlive.devices.eltex.parsers import parse_show_version
from switchlive.devices.eltex.profiles import get_profile_for_model
from switchlive.devices.registry import register_detector

log = logging.getLogger(__name__)


@register_detector("eltex")
class EltexDetector(DeviceDetector):
    """Detector for Eltex MES switches."""

    def can_detect(self, session: DeviceSession) -> bool:
        try:
            result = session.run_command("show version", timeout=5.0)
            if not result.success:
                return False
            text = result.output
            return "Eltex" in text or "MES2324B" in text or "MES2324FB" in text
        except Exception:
            return False

    def identify(self, session: DeviceSession) -> DeviceIdentity:
        result = session.run_command("show version", timeout=10.0)
        identity = parse_show_version(result.output)
        if identity.model == "unknown":
            log.warning("Eltex detected but model unknown")
        elif get_profile_for_model(identity.model) is None:
            log.info("No profile for Eltex model: %s", identity.model)
        return identity
