"""Обработка CLI-пейджеров (More, --More--, и т.д.).

Пейджер — это когда устройство выводит данные постранично и ждёт
нажатия клавиши для продолжения. Session должна это обрабатывать.
"""

from __future__ import annotations

import re

ANSI_PATTERN = r"\x1b\[[0-9;?]*[A-Za-z]"

# Паттерны пейджеров
PAGER_PATTERNS = [
    r"(?i)--\s*more\s*--",
    r"(?i)\bmore\b\s*$",
    r"(?i)press\s+any\s+key",
    r"(?i)press\s+q\s+to\s+quit",
    r"(?i)press\s+space\s+to\s+continue",
    r"(?i)\(q\s+to\s+quit\)",
    r"(?is)q\s+Quit.*SPACE.*Next\s+Page",
    r"(?is)CTRL\+C.*ESC.*Quit.*Next\s+(?:Page|Entry)",
]

# Ответы
SPACE_RESPONSE = b" "
ENTER_RESPONSE = b"\r\n"
QUIT_RESPONSE = b"q"


def detect_pager(text: str) -> bool:
    """Обнаружить пейджер в выводе."""
    normalized = _strip_ansi(text)
    return any(re.search(p, normalized) for p in PAGER_PATTERNS)


def pager_space() -> bytes:
    """Пробел — пролистать дальше."""
    return SPACE_RESPONSE


def pager_quit() -> bytes:
    """q — прервать вывод."""
    return QUIT_RESPONSE


def strip_pager_artifacts(text: str) -> str:
    """Убрать артефакты пейджера из вывода (--More--, и т.д.)."""
    cleaned = _strip_ansi(text)
    for pattern in PAGER_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    # Убрать лишние пустые строки после очистки
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned


def _strip_ansi(text: str) -> str:
    return re.sub(ANSI_PATTERN, "", text)
