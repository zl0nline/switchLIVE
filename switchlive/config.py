"""Загрузка и валидация конфигурации."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Config:
    """Конфигурация switchLIVE."""

    # Настройки iperf
    iperf_server_host: str | None = None
    iperf_server_port: int = 5201
    iperf_duration: int = 10
    iperf_parallel_streams: int = 4
    iperf_min_throughput_mbps: float = 50.0
    iperf_max_loss_percent: float = 5.0

    # Настройки тестирования
    link_timeout_sec: int = 30
    poe_timeout_sec: int = 180
    max_timeout_sec: int = 600

    # Файлы
    standard_login_file: str = "standart_login.txt"
    report_dir: str = "reports"

    # Хранилище
    db_path: str = "switchlive.db"

    # Прочее
    debug: bool = False
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Config:
        normalized = dict(data)
        if isinstance(data.get("iperf"), dict):
            iperf = data["iperf"]
            normalized.setdefault("iperf_server_host", iperf.get("server_host"))
            normalized.setdefault("iperf_server_port", iperf.get("server_port"))
            normalized.setdefault("iperf_duration", iperf.get("duration_sec"))
            normalized.setdefault("iperf_parallel_streams", iperf.get("parallel_streams"))
            normalized.setdefault("iperf_min_throughput_mbps", iperf.get("min_throughput_mbps"))
            normalized.setdefault("iperf_max_loss_percent", iperf.get("max_loss_percent"))
        if isinstance(data.get("timeouts"), dict):
            timeouts = data["timeouts"]
            normalized.setdefault("link_timeout_sec", timeouts.get("link_sec"))
            normalized.setdefault("poe_timeout_sec", timeouts.get("poe_sec"))
            normalized.setdefault("max_timeout_sec", timeouts.get("max_sec"))
        if isinstance(data.get("reports"), dict):
            reports = data["reports"]
            normalized.setdefault("report_dir", reports.get("report_dir"))
            normalized.setdefault("db_path", reports.get("db_path"))

        known = {f.name for f in cls.__dataclass_fields__.values()} - {"extra"}
        kwargs = {
            k: v
            for k, v in normalized.items()
            if k in known and v is not None
        }
        extra = {k: v for k, v in data.items() if k not in known}
        obj = cls(**kwargs)
        obj.extra = extra
        return obj

    @classmethod
    def load(cls, path: str | Path) -> Config:
        p = Path(path)
        if not p.exists():
            return cls()
        text = p.read_text(encoding="utf-8")
        if p.suffix == ".json":
            return cls.from_dict(json.loads(text))
        # Минимальный YAML-парсер не тащим — ждём JSON
        raise ValueError(f"Unsupported config format: {p.suffix}")
