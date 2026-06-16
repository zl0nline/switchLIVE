"""D-Link детектор устройства.

Пытается определить, что подключённое устройство — D-Link коммутатор,
и извлечь модель/серийник/прошивку.
"""

from __future__ import annotations

import logging

from switchlive.core.models import DeviceIdentity
from switchlive.devices.base import DeviceDetector, DeviceSession
from switchlive.devices.dlink.parsers import parse_show_switch
from switchlive.devices.dlink.profiles import get_profile_for_model
from switchlive.devices.registry import register_detector

log = logging.getLogger(__name__)


@register_detector("dlink")
class DLinkDetector(DeviceDetector):
    """Детектор D-Link коммутаторов."""

    def can_detect(self, session: DeviceSession) -> bool:
        """Быстрая проверка: D-Link или нет.

        Выполняет 'show switch' и смотрит на вывод.
        """
        try:
            result = session.run_command("show switch", timeout=5.0)
            if not result.success:
                return False
            text = result.output
            # D-Link признаки в выводе
            if "D-Link" in text or "DES-" in text or "DGS-" in text:
                return True
            # Иногда только "Device Type:" без D-Link
            if "Device Type:" in text and "Firmware Version:" in text:
                return True
            return False
        except Exception:
            return False

    def identify(self, session: DeviceSession) -> DeviceIdentity:
        """Полная идентификация D-Link устройства."""
        result = session.run_command("show switch", timeout=10.0)
        identity = parse_show_switch(result.output)

        if identity.model == "unknown":
            log.warning("D-Link detected but model unknown")

        # Проверяем, есть ли профиль для этой модели
        profile = get_profile_for_model(identity.model)
        if profile is None:
            log.info("No profile for D-Link model: %s", identity.model)

        return identity
