"""PoE probe — нормализованный тест питания PoE (#11).

Vendor-agnostic: возвращает нормализованный PoEResult.
Vendor-специфичные строки остаются в D-Link parser/adapter.

Логика:
1. Запросить PoE-статус через adapter.
2. Нормализовать: enabled, powered, class, power_w, fault.
3. Если PoE-камера — дождаться загрузки и провернуть network visibility.
4. Вернуть отдельный PoE-вердикт (не зависит от Ethernet).
"""

from __future__ import annotations

import logging
import socket
import time
from dataclasses import dataclass, field
from enum import Enum

from switchlive.core.models import PortInfo
from switchlive.devices.base import DeviceAdapter, DeviceSession

log = logging.getLogger(__name__)


class PoEState(str, Enum):
    """Нормализованное состояние PoE на порту."""

    POWERED = "powered"          # питание подаётся
    DELIVERING = "delivering"    # питание подаётся, камера грузится
    NOT_POWERED = "not_powered"  # PoE включён, но не выдаёт
    DISABLED = "disabled"        # PoE выключен на порту
    FAULT = "fault"              # ошибка PoE
    UNKNOWN = "unknown"


class PoEVerdict(str, Enum):
    """Вердикт PoE-теста — независимый от Ethernet."""

    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"
    SKIP = "SKIP"  # PoE не поддерживается


@dataclass
class PoEResult:
    """Нормализованный результат PoE-теста.

    Не содержит vendor-специфичных строк.
    """

    verdict: PoEVerdict = PoEVerdict.WARN
    state: PoEState = PoEState.UNKNOWN
    enabled: bool = False       # PoE admin status
    powered: bool = False       # фактическая выдача питания
    poe_class: str = ""         # 0, 1, 2, 3, 4
    power_w: float = 0.0        # фактическое потребление
    fault: str = ""             # описание ошибки если есть
    camera_reachable: bool = False  # камера видна в сети
    camera_ip: str = ""
    notes: list[str] = field(default_factory=list)
    boot_time_sec: float = 0.0  # сколько ждали загрузку камеры


def probe_poe_status(
    adapter: DeviceAdapter,
    session: DeviceSession,
    port: PortInfo,
) -> PoEResult:
    """Запросить PoE-статус порта через adapter.

    Возвращает нормализованный PoEResult.
    Если adapter не поддерживает PoE — verdict=SKIP.
    """
    if not port.supports_poe:
        return PoEResult(verdict=PoEVerdict.SKIP, notes=["PoE не поддерживается портом"])

    if not hasattr(adapter, "get_poe_status"):
        return PoEResult(verdict=PoEVerdict.SKIP, notes=["Adapter не поддерживает PoE"])

    try:
        raw = adapter.get_poe_status(session, port)
    except Exception as e:
        return PoEResult(
            verdict=PoEVerdict.WARN,
            notes=[f"PoE query failed: {e}"],
        )

    if not raw:
        return PoEResult(
            verdict=PoEVerdict.WARN,
            notes=["PoE: пустой ответ от adapter"],
        )

    # Нормализация vendor-агностик
    return _normalize_poe(raw)


def wait_for_camera(
    camera_ip: str,
    timeout: float = 180.0,
    check_interval: float = 5.0,
    progress_callback=None,
) -> tuple[bool, float]:
    """Дождаться загрузки PoE-камеры и её доступности по сети.

    Args:
        camera_ip: IP-адрес камеры.
        timeout: максимальное ожидание (сек).
        check_interval: интервал проверок (сек).
        progress_callback: функция(message: str).

    Returns:
        (reachable: bool, waited_sec: float)
    """
    def _progress(msg: str) -> None:
        log.info("PoE camera: %s", msg)
        if progress_callback:
            progress_callback(msg)

    start = time.monotonic()
    deadline = start + timeout

    _progress(f"Ожидание камеры {camera_ip} (до {timeout:.0f}s)...")

    while time.monotonic() < deadline:
        if _check_tcp_reachable(camera_ip, 80, timeout=3.0):
            waited = time.monotonic() - start
            _progress(f"Камера доступна ({waited:.0f}s)")
            return True, waited

        # Прогресс-индикация
        elapsed = time.monotonic() - start
        _progress(f"Камера грузится... {elapsed:.0f}s / {timeout:.0f}s")

        time.sleep(check_interval)

    waited = time.monotonic() - start
    _progress(f"⚠️ Камера не ответила за {timeout:.0f}s")
    return False, waited


def evaluate_poe_verdict(
    poe: PoEResult,
    camera_reachable: bool | None = None,
    poe_timeout_sec: float = 180.0,
) -> PoEResult:
    """Оценить итоговый PoE-вердикт.

    Ethernet и PoE вердикты независимы:
    - Порт может PASS Ethernet, но FAIL PoE.
    - Порт может FAIL Ethernet, но PoE не при чём (SKIP).
    """
    if poe.verdict == PoEVerdict.SKIP:
        return poe

    # Fault = FAIL
    if poe.state == PoEState.FAULT or poe.fault:
        poe.verdict = PoEVerdict.FAIL
        poe.notes.append(f"PoE fault: {poe.fault}")
        return poe

    # Не включён = SKIP (не ошибка если порт не PoE)
    if poe.state == PoEState.DISABLED:
        poe.verdict = PoEVerdict.SKIP
        poe.notes.append("PoE выключен на порту")
        return poe

    # Включён, но не выдаёт = FAIL
    if poe.state in (PoEState.NOT_POWERED, PoEState.UNKNOWN) and not poe.powered:
        poe.verdict = PoEVerdict.WARN
        poe.notes.append("PoE включён, но питание не выдаётся")
        return poe

    # Питание есть → проверяем камеру, если она настроена.
    if camera_reachable is None:
        poe.verdict = PoEVerdict.PASS
        poe.notes.append("PoE питание подаётся")
    elif camera_reachable:
        poe.verdict = PoEVerdict.PASS
        poe.camera_reachable = True
        poe.notes.append(f"Камера видна: {poe.camera_ip or 'OK'}")
    else:
        # Питание есть, но камера не ответила
        poe.verdict = PoEVerdict.WARN
        poe.notes.append("Питание есть, камера не ответила")

    return poe


# --- Внутренние ---

def _normalize_poe(raw: dict) -> PoEResult:
    """Нормализовать vendor-специфичный вывод в PoEResult."""
    result = PoEResult()

    # Status / state
    status_str = str(raw.get("status", raw.get("state", ""))).upper().strip()
    if status_str in ("ON", "ENABLED", "DELIVERING", "POWERED", "POWER_GOOD"):
        result.enabled = True
        result.powered = True
        result.state = PoEState.POWERED
    elif status_str in ("OFF", "DISABLED", "ADMIN_DISABLE"):
        result.enabled = False
        result.state = PoEState.DISABLED
    elif status_str in ("FAULT", "ERROR", "OVERLOAD", "SHORT"):
        result.enabled = True
        result.state = PoEState.FAULT
        result.fault = status_str
    elif status_str in ("SEARCHING", "DETECTING"):
        result.enabled = True
        result.state = PoEState.NOT_POWERED
    else:
        result.state = PoEState.UNKNOWN

    # Class
    cls = raw.get("class", raw.get("poe_class", ""))
    result.poe_class = str(cls) if cls else ""

    # Power
    power = raw.get("power_w", raw.get("power", raw.get("wattage", 0)))
    try:
        result.power_w = float(power) if power else 0.0
    except (ValueError, TypeError):
        result.power_w = 0.0

    # Fault string
    if "fault" in raw:
        result.fault = str(raw["fault"])

    return result


def _check_tcp_reachable(host: str, port: int = 80, timeout: float = 3.0) -> bool:
    """Проверить TCP-доступность (HTTP/RTSP порт камеры)."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (OSError, socket.error):
        return False
