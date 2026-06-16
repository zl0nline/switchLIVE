"""Шаблоны промптов для разных вендоров.

Session использует эти паттерны для определения состояния CLI.
Вендоры могут добавлять свои паттерны через DeviceProfile.
"""

from __future__ import annotations

import re

# --- Login / Password промпты ---

LOGIN_PATTERNS = [
    r"(?i)login\s*:?\s*$",
    r"(?i)user\s*name\s*:?\s*$",
    r"(?i)account\s*:?\s*$",
    r"(?i)user\s*:?\s*$",
]

PASSWORD_PATTERNS = [
    r"(?i)password\s*:?\s*$",
    r"(?i)passwd\s*:?\s*$",
]

# --- Командные промпты по вендорам ---

COMMAND_PROMPTS: dict[str, list[str]] = {
    "dlink": [
        r"[\w\-_.]+:>",           # D-Link user mode
        r"[\w\-_.]+:#",           # D-Link enable mode
    ],
    "cisco": [
        r"[\w\-_.]+>",            # Cisco user mode
        r"[\w\-_.]+#",            # Cisco enable mode
    ],
    "huawei": [
        r"<[\w\-_.]+>",           # Huawei user view
        r"\[[\w\-_.]+\]",         # Huawei system view
    ],
    "eltex": [
        r"[\w\-_.]+>",            # Eltex user mode
        r"[\w\-_.]+#",            # Eltex enable mode
    ],
    "edgecore": [
        r"[\w\-_.]+>",            # Edge-Core user mode
        r"[\w\-_.]+#",            # Edge-Core enable mode
    ],
    "generic": [
        r"[\w\-_.]+[>#]\s*$",
        r"[\w\-_.]+:\w+\s*$",
    ],
}

# --- Login failed ---

LOGIN_FAILED_PATTERNS = [
    r"(?i)(login\s+invalid|access\s+denied|authenticat|fail|incorrect|bad\s+password)",
]


def match_any(text: str, patterns: list[str]) -> bool:
    return any(re.search(p, text, re.MULTILINE) for p in patterns)


def match_login_prompt(text: str) -> bool:
    return match_any(text, LOGIN_PATTERNS)


def match_password_prompt(text: str) -> bool:
    return match_any(text, PASSWORD_PATTERNS)


def match_login_failed(text: str) -> bool:
    return match_any(text, LOGIN_FAILED_PATTERNS)


def find_command_prompt(text: str, vendor: str = "generic") -> str | None:
    """Найти командный промпт в тексте. Возвращает matched prompt или None."""
    patterns = COMMAND_PROMPTS.get(vendor, COMMAND_PROMPTS["generic"])
    for pattern in patterns:
        match = re.search(pattern, text, re.MULTILINE)
        if match:
            return match.group(0).strip()
    return None
