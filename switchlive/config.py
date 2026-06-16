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

    # Настройки тестирования
    link_timeout_sec: int = 30
    poe_timeout_sec: int = 180

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
        known = {f.name for f in cls.__dataclass_fields__.values()} - {"extra"}
        kwargs = {k: v for k, v in data.items() if k in known}
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
