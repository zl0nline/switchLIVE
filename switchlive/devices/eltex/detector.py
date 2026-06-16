"""Eltex детектор устройства."""

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
    """Детектор Eltex MES23xx коммутаторов."""

    def can_detect(self, session: DeviceSession) -> bool:
        try:
            result = session.run_command("show version", timeout=5.0)
            if not result.success:
                return False
            text = result.output
            if "Eltex" in text or "MES" in text:
                return True
            if "Machine Description" in text and "Software Version" in text:
                return True
            return False
        except Exception:
            return False

    def identify(self, session: DeviceSession) -> DeviceIdentity:
        result = session.run_command("show version", timeout=10.0)
        identity = parse_show_version(result.output)

        if identity.model == "unknown":
            log.warning("Eltex detected but model unknown")

        profile = get_profile_for_model(identity.model)
        if profile is None:
            log.info("No profile for Eltex model: %s", identity.model)

        return identity
