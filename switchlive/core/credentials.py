"""Учётные данные для авторизации на устройствах."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class Credentials:
    username: str = ""
    password: str = ""
    enable_password: str = ""


def load_standard_logins(path: str | Path) -> list[Credentials]:
    """Загрузить стандартные логины/пароли из файла.

    Формат файла — построчно: username password [enable_password]
    Пустые строки и строки начиная с # игнорируются.
    """
    p = Path(path)
    if not p.exists():
        return []

    creds = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) >= 2:
            cred = Credentials(
                username=parts[0],
                password=parts[1],
                enable_password=parts[2] if len(parts) >= 3 else "",
            )
            creds.append(cred)
    return creds
