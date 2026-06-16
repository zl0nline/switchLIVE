"""Обработка CLI-пейджеров (More, --More--, и т.д.)."""

from __future__ import annotations

import re

PAGER_PATTERNS = [
    r"(?i)--\s*more\s*--",
    r"(?i)\bmore\b.*$",
    r"(?i)press\s+any\s+key",
    r"(?i)press\s+q\s+to\s+quit",
]

PAGER_RESPONSE = b" "
QUIT_RESPONSE = b"q"


def detect_pager(text: str) -> bool:
    """Обнаружить пейджер в выводе."""
    return any(re.search(p, text) for p in PAGER_PATTERNS)


def pager_response() -> bytes:
    """Ответ для пролистывания пейджера (пробел)."""
    return PAGER_RESPONSE
