"""Шаблоны промптов и парсинг вывода."""

from __future__ import annotations

import re

# Общие паттерны промптов
LOGIN_PROMPTS = [
    r"(?i)login\s*:?\s*$",
    r"(?i)user\s*name\s*:?\s*$",
    r"(?i)account\s*:?\s*$",
]

PASSWORD_PROMPTS = [
    r"(?i)password\s*:?\s*$",
]

# Паттерны командного промпта по вендорам
COMMAND_PROMPTS = {
    "dlink": [
        r"[\w\-_.]+:>",       # D-Link user mode
        r"[\w\-_.]+:#",       # D-Link enable mode
    ],
    "cisco": [
        r"[\w\-_.]+>",        # Cisco user mode
        r"[\w\-_.]+#",        # Cisco enable mode
    ],
    "huawei": [
        r"<[\w\-_.]+>",       # Huawei user view
        r"\[[\w\-_.]+\]",     # Huawei system view
    ],
    "eltex": [
        r"[\w\-_.]+>",        # Eltex user mode
        r"[\w\-_.]+#",        # Eltex enable mode
    ],
    "generic": [
        r"[\w\-_.]+[>#]\s*$",
    ],
}


def match_login_prompt(text: str) -> bool:
    return any(re.search(p, text) for p in LOGIN_PROMPTS)


def match_password_prompt(text: str) -> bool:
    return any(re.search(p, text) for p in PASSWORD_PROMPTS)


def match_command_prompt(text: str, vendor: str = "generic") -> str | None:
    """Найти командный промпт в тексте. Возвращает matched prompt или None."""
    patterns = COMMAND_PROMPTS.get(vendor, COMMAND_PROMPTS["generic"])
    for pattern in patterns:
        match = re.search(pattern, text, re.MULTILINE)
        if match:
            return match.group(0).strip()
    return None
