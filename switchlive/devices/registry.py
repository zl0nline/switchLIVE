"""Реестр адаптеров и профилей устройств."""

from __future__ import annotations

from switchlive.devices.base import DeviceAdapter

_REGISTRY: dict[str, type[DeviceAdapter]] = {}


def register_adapter(vendor: str, model_pattern: str):
    """Декоратор для регистрации адаптера.

    @register_adapter("dlink", "DES-1228")
    class DES1228Adapter(DeviceAdapter):
        ...
    """
    def decorator(cls: type[DeviceAdapter]) -> type[DeviceAdapter]:
        key = f"{vendor}:{model_pattern}"
        _REGISTRY[key] = cls
        return cls
    return decorator


def find_adapter(vendor: str, model: str) -> DeviceAdapter | None:
    """Найти адаптер по vendor и модели. Точное совпадение, затем префикс."""
    # Точное совпадение
    key = f"{vendor}:{model}"
    if key in _REGISTRY:
        return _REGISTRY[key]()

    # По префиксу модели
    for k, cls in _REGISTRY.items():
        v, m = k.split(":", 1)
        if v == vendor and model.startswith(m):
            return cls()

    return None


def list_supported() -> list[str]:
    """Список зарегистрированных vendor:model."""
    return sorted(_REGISTRY.keys())
