"""Реестр адаптеров, профилей и детекторов устройств.

Регистрация через декораторы:
    @register_adapter("dlink", "DES-1228")
    @register_detector("dlink")
"""

from __future__ import annotations

from switchlive.devices.base import DeviceAdapter, DeviceDetector

# --- Реестры ---

_ADAPTERS: dict[str, type[DeviceAdapter]] = {}
_DETECTORS: dict[str, type[DeviceDetector]] = {}


# --- Адаптеры ---

def register_adapter(vendor: str, model_pattern: str):
    """Декоратор для регистрации адаптера под модель.

    @register_adapter("dlink", "DES-1228")
    class DES1228Adapter(DeviceAdapter):
        ...
    """
    def decorator(cls: type[DeviceAdapter]) -> type[DeviceAdapter]:
        key = f"{vendor}:{model_pattern}"
        _ADAPTERS[key] = cls
        return cls
    return decorator


def find_adapter(vendor: str, model: str) -> DeviceAdapter | None:
    """Найти адаптер по vendor и модели. Точное совпадение, затем префикс."""
    # Точное совпадение
    key = f"{vendor}:{model}"
    if key in _ADAPTERS:
        return _ADAPTERS[key]()

    # По префиксу модели (для семейств)
    best_match = None
    best_len = 0
    for k, cls in _ADAPTERS.items():
        v, m = k.split(":", 1)
        if v == vendor and model.startswith(m) and len(m) > best_len:
            best_match = cls
            best_len = len(m)

    return best_match() if best_match else None


# --- Детекторы ---

def register_detector(vendor: str):
    """Декоратор для регистрации детектора под вендор.

    @register_detector("dlink")
    class DLinkDetector(DeviceDetector):
        ...
    """
    def decorator(cls: type[DeviceDetector]) -> type[DeviceDetector]:
        _DETECTORS[vendor] = cls
        return cls
    return decorator


def get_all_detectors() -> list[DeviceDetector]:
    """Вернуть список всех зарегистрированных детекторов."""
    return [cls() for cls in _DETECTORS.values()]


def get_detector(vendor: str) -> DeviceDetector | None:
    """Получить детектор по вендору."""
    cls = _DETECTORS.get(vendor)
    return cls() if cls else None


# --- Информация ---

def list_supported() -> list[str]:
    """Список зарегистрированных vendor:model."""
    return sorted(_ADAPTERS.keys())


def list_detector_vendors() -> list[str]:
    """Список зарегистрированных вендоров-детекторов."""
    return sorted(_DETECTORS.keys())
