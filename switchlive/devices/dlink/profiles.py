"""D-Link профили коммутаторов.

Группировка по семействам (CLI-compatible):
- DES-1xxx/3xxx: старые L2 (DES-1228, DES-3200, DES-3028, DES-3526)
- DGS-1210: управляемые L2+
- DGS-3000/3100/3120: L2+ агрегация
- DGS-36xx: L3 стекируемые

Каждое семейство — свой миксин с общими командами.
Модели внутри семейства могут отличаться количеством портов.
"""

from __future__ import annotations

from switchlive.core.models import DeviceCategory, PortInfo
from switchlive.devices.base import DeviceProfile

# --- Базовые D-Link общие настройки ---

class DLinkBase(DeviceProfile):
    """База для всех D-Link коммутаторов."""

    vendor = "D-Link"
    category = DeviceCategory.SWITCH.value
    prompt_vendor = "dlink"
    disable_paging_cmd = "disable clipaging"

    # Команды (общие для большинства D-Link)
    show_version_cmd = "show switch"
    show_ports_cmd = "show ports"
    show_macs_cmd = "show fdb"
    show_counters_cmd = "show ports {port} counters"
    shutdown_cmd = "config ports {port} state disable"
    no_shutdown_cmd = "config ports {port} state enable"
    save_config_cmd = "save"
    reload_cmd = "reboot"

    show_transceiver_cmd = "show transceiver"
    factory_reset_cmd = "reset config"


# --- Семейства ---

class DLinkDES12xx(DLinkBase):
    """DES-1228 и совместимые."""

    model = "DES-1228"
    family = "DES-12xx"

    supports_poe = False
    supports_sfp = True

    @property
    def ports(self) -> list[PortInfo]:
        return [
            PortInfo(index=i, name=str(i), speed_mbps=100, media="copper", connector="RJ45")
            for i in range(1, 25)
        ] + [
            PortInfo(index=25, name="25", speed_mbps=1000, media="copper", connector="RJ45", role="uplink"),
            PortInfo(index=26, name="26", speed_mbps=1000, media="copper", connector="RJ45", role="uplink"),
            PortInfo(index=27, name="27", speed_mbps=1000, media="combo", connector="RJ45/SFP", role="combo"),
            PortInfo(index=28, name="28", speed_mbps=1000, media="combo", connector="RJ45/SFP", role="combo"),
        ]


class DLinkDES32xx(DLinkBase):
    """DES-3200-10, DES-3200, DES-3200-C1."""

    model = "DES-3200-10"
    family = "DES-32xx"

    supports_poe = False
    supports_sfp = True

    @property
    def ports(self) -> list[PortInfo]:
        return [
            PortInfo(
                index=i,
                name=str(i),
                speed_mbps=100,
                media="copper",
                connector="RJ45",
            )
            for i in range(1, 9)
        ] + [
            PortInfo(index=9, name="9", speed_mbps=1000, media="combo", connector="RJ45/SFP", role="combo"),
            PortInfo(index=10, name="10", speed_mbps=1000, media="combo", connector="RJ45/SFP", role="combo"),
        ]


class DLinkDES3200(DLinkDES32xx):
    """DES-3200 alias profile."""

    model = "DES-3200"


class DLinkDES3200C1(DLinkDES32xx):
    """DES-3200-C1 alias profile."""

    model = "DES-3200-C1"


class DLinkDES3028(DLinkBase):
    """DES-3028."""

    model = "DES-3028"
    family = "DES-30xx"

    supports_poe = False
    supports_sfp = True

    @property
    def ports(self) -> list[PortInfo]:
        return [
            PortInfo(index=i, name=str(i), speed_mbps=100, media="copper", connector="RJ45")
            for i in range(1, 25)
        ] + [
            PortInfo(index=25, name="25", speed_mbps=1000, media="copper", connector="RJ45", role="uplink"),
            PortInfo(index=26, name="26", speed_mbps=1000, media="copper", connector="RJ45", role="uplink"),
            PortInfo(index=27, name="27", speed_mbps=1000, media="combo", connector="RJ45/SFP", role="combo"),
            PortInfo(index=28, name="28", speed_mbps=1000, media="combo", connector="RJ45/SFP", role="combo"),
        ]


class DLinkDES3526(DLinkBase):
    """DES-3526."""

    model = "DES-3526"
    family = "DES-35xx"

    supports_poe = False
    supports_sfp = True

    @property
    def ports(self) -> list[PortInfo]:
        return [
            PortInfo(index=i, name=str(i), speed_mbps=100, media="copper", connector="RJ45")
            for i in range(1, 25)
        ] + [
            PortInfo(index=25, name="25", speed_mbps=1000, media="combo", connector="RJ45/SFP", role="combo"),
            PortInfo(index=26, name="26", speed_mbps=1000, media="combo", connector="RJ45/SFP", role="combo"),
        ]


class DLinkDGS1210(DLinkBase):
    """DGS-1210-28/ME, DGS-1210-28/SX."""

    model = "DGS-1210-28/ME"
    family = "DGS-1210"

    supports_poe = False
    supports_sfp = True

    @property
    def ports(self) -> list[PortInfo]:
        return [
            PortInfo(index=i, name=str(i), speed_mbps=1000, media="copper", connector="RJ45")
            for i in range(1, 25)
        ] + [
            PortInfo(index=25, name="25", speed_mbps=1000, media="sfp", connector="SFP", role="uplink"),
            PortInfo(index=26, name="26", speed_mbps=1000, media="sfp", connector="SFP", role="uplink"),
            PortInfo(index=27, name="27", speed_mbps=1000, media="sfp", connector="SFP", role="uplink"),
            PortInfo(index=28, name="28", speed_mbps=1000, media="sfp", connector="SFP", role="uplink"),
        ]


class DLinkDGS1210SX(DLinkDGS1210):
    """DGS-1210-28/SX alias profile."""

    model = "DGS-1210-28/SX"


class DLinkDGS3000(DLinkBase):
    """DGS-3000-10."""

    model = "DGS-3000-10"
    family = "DGS-3000"

    supports_poe = False
    supports_sfp = True

    @property
    def ports(self) -> list[PortInfo]:
        return [
            PortInfo(
                index=i,
                name=str(i),
                speed_mbps=1000,
                media="copper",
                connector="RJ45",
            )
            for i in range(1, 9)
        ] + [
            PortInfo(index=9, name="9", speed_mbps=1000, media="combo", connector="RJ45/SFP", role="combo"),
            PortInfo(index=10, name="10", speed_mbps=1000, media="combo", connector="RJ45/SFP", role="combo"),
        ]


class DLinkDGS3100(DLinkBase):
    """DGS-3100-24/TC."""

    model = "DGS-3100-24/TC"
    family = "DGS-3100"

    supports_poe = False
    supports_sfp = True

    @property
    def ports(self) -> list[PortInfo]:
        return [
            PortInfo(
                index=i,
                name=str(i),
                speed_mbps=1000,
                media="copper",
                connector="RJ45",
            )
            for i in range(1, 21)
        ] + [
            PortInfo(index=i, name=str(i), speed_mbps=1000, media="combo", connector="RJ45/SFP", role="combo")
            for i in range(21, 25)
        ]


class DLinkDGS3120(DLinkBase):
    """DGS-3120-24/SC."""

    model = "DGS-3120-24/SC"
    family = "DGS-3120"

    supports_poe = False
    supports_sfp = True

    @property
    def ports(self) -> list[PortInfo]:
        return [
            PortInfo(
                index=i,
                name=str(i),
                speed_mbps=1000,
                media="sfp",
                connector="SFP",
            )
            for i in range(1, 17)
        ] + [
            PortInfo(index=i, name=str(i), speed_mbps=1000, media="combo", connector="RJ45/SFP", role="combo")
            for i in range(17, 25)
        ]


class DLinkDGS36xx(DLinkBase):
    """DGS-3612, DGS-3620/SC, DGS-3627, DGS-3630/SC."""

    model = "DGS-3620/SC"
    family = "DGS-36xx"

    supports_poe = False
    supports_sfp = True
    supports_dom = True

    show_poe_cmd = ""
    poe_enable_cmd = ""

    @property
    def ports(self) -> list[PortInfo]:
        # Базовый шаблон — конкретная модель уточнит
        return [
            PortInfo(
                index=i,
                name=str(i),
                speed_mbps=1000,
                media="sfp",
                connector="SFP",
            )
            for i in range(1, 21)
        ] + [
            PortInfo(index=i, name=str(i), speed_mbps=1000, media="combo", connector="RJ45/SFP", role="combo")
            for i in range(21, 25)
        ] + [
            PortInfo(index=i, name=str(i), speed_mbps=10000, media="sfp_plus", connector="SFP+", role="uplink")
            for i in range(25, 29)
        ]


class DLinkDGS3612(DLinkDGS36xx):
    """DGS-3612 — 12x1G + 4xcombo SFP."""

    model = "DGS-3612"

    @property
    def ports(self) -> list[PortInfo]:
        return [
            PortInfo(
                index=i,
                name=str(i),
                speed_mbps=1000,
                media="copper",
                connector="RJ45",
            )
            for i in range(1, 13)
        ] + [
            PortInfo(index=i, name=str(i), speed_mbps=1000, media="combo", connector="RJ45/SFP", role="combo")
            for i in range(13, 17)
        ]


class DLinkDGS3630SC(DLinkDGS36xx):
    """DGS-3630/SC — same physical layout as DGS-3620-28SC."""

    model = "DGS-3630/SC"


class DLinkDGS3627(DLinkDGS36xx):
    """DGS-3627 — 24x1G + 4xcombo SFP."""

    model = "DGS-3627"

    @property
    def ports(self) -> list[PortInfo]:
        return [
            PortInfo(
                index=i,
                name=str(i),
                speed_mbps=1000,
                media="copper",
                connector="RJ45",
            )
            for i in range(1, 25)
        ] + [
            PortInfo(index=i, name=str(i), speed_mbps=1000, media="combo", connector="RJ45/SFP", role="combo")
            for i in range(25, 29)
        ]


class DLinkDGS3420(DLinkBase):
    """DGS-3420/SC."""

    model = "DGS-3420/SC"
    family = "DGS-34xx"

    supports_poe = False
    supports_sfp = True
    supports_dom = True

    show_poe_cmd = ""
    poe_enable_cmd = ""

    @property
    def ports(self) -> list[PortInfo]:
        return [
            PortInfo(
                index=i,
                name=str(i),
                speed_mbps=1000,
                media="sfp",
                connector="SFP",
            )
            for i in range(1, 21)
        ] + [
            PortInfo(index=i, name=str(i), speed_mbps=1000, media="combo", connector="RJ45/SFP", role="combo")
            for i in range(21, 25)
        ] + [
            PortInfo(index=25, name="25", speed_mbps=10000, media="sfp_plus", connector="SFP+", role="uplink"),
            PortInfo(index=26, name="26", speed_mbps=10000, media="sfp_plus", connector="SFP+", role="uplink"),
        ]


# --- Реестр моделей → профиль ---

# Карта: строка модели (из CLI) → класс профиля
# Используется детектором для подбора профиля
MODEL_MAP: dict[str, type[DLinkBase]] = {
    # Частые
    "DES-1228": DLinkDES12xx,
    "DES-3200-10": DLinkDES32xx,
    "DGS-3000-10": DLinkDGS3000,
    "DGS-1210-28/ME": DLinkDGS1210,
    "DGS-1210-28/SX": DLinkDGS1210SX,
    "DGS-3100-24/TC": DLinkDGS3100,
    "DGS-3120-24/SC": DLinkDGS3120,
    "DGS-3612": DLinkDGS3612,
    "DGS-3620/SC": DLinkDGS36xx,
    "DGS-3630/SC": DLinkDGS3630SC,
    "DGS-3420/SC": DLinkDGS3420,
    "DGS-3627": DLinkDGS3627,
    # Редкие
    "DES-3200": DLinkDES3200,
    "DES-3200-C1": DLinkDES3200C1,
    "DES-3028": DLinkDES3028,
    "DES-3526": DLinkDES3526,
}


def get_profile_for_model(model_str: str) -> DLinkBase | None:
    """Подобрать профиль по строке модели.

    Сначала точное совпадение, затем префикс семейства.
    """
    # Точное совпадение
    if model_str in MODEL_MAP:
        return MODEL_MAP[model_str]()

    # По префиксу (например "DGS-1210-28/ME fast" → DGS-1210)
    for key, cls in MODEL_MAP.items():
        if model_str.startswith(key) or key.startswith(model_str[:8]):
            return cls()

    return None
