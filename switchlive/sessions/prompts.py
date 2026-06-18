"""Шаблоны промптов для разных вендоров.

Session использует эти паттерны для определения состояния CLI.
Вендоры могут добавлять свои паттерны через DeviceProfile.

Важно: разделяем «последнее состояние» (last chunk / last line) и
«поиск по всему transcript». Login flow работает по последнему чанку,
чтобы не матчить устаревшие промпты.
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
        r"[\w\-_.]+:[\w\-_.]+[>#]",  # D-Link prompt with username
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
    # Универсальный режим для discovery — неизвестно, какой вендор на линии.
    # Включает паттерны всех вендоров, чтобы детектить промпты любого устройства.
    "discovery": [
        # D-Link (двоеточие в промпте)
        r"[\w\-_.]+:[\w\-_.]*[>#]",  # device:# device:admin# device:>
        # Cisco / Eltex / Edge-Core (без двоеточия)
        r"[\w\-_.]+>\s*$",           # switch>
        r"[\w\-_.]+#\s*$",           # switch#
        # Huawei
        r"<[\w\-_.]+>",              # <HUAWEI>
        r"\[[\w\-_.]+\]",            # [HUAWEI]
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

AUTH_RETRY_PATTERNS = [
    r"(?i)press\s+enter\s+key\s+to\s+retry\s+authentication",
]

AUTH_LOCKOUT_PATTERNS = [
    r"(?i)blocked\s+unauthorized\s+cli\s+access",
    r"(?i)maximum\s+number\s+of\s+login\s+attempts\s+reached",
    r"(?i)lock\s*out\s+for\s+(\d+)\s+seconds?",
    r"(?i)locked\s+out\s+for\s+(\d+)\s+seconds?",
]


def _last_nonempty_line(text: str) -> str:
    """Вернуть последнюю непустую строку после очистки."""
    lines = text.replace("\r", "").rstrip().split("\n")
    for line in reversed(lines):
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def match_login_current(chunk: str) -> bool:
    """Смотрит последнюю непустую строку чанка — нужен ли login."""
    line = _last_nonempty_line(chunk)
    return any(re.search(p, line) for p in LOGIN_PATTERNS)


def match_password_current(chunk: str) -> bool:
    """Смотрит последнюю непустую строку чанка — нужен ли пароль."""
    line = _last_nonempty_line(chunk)
    return any(re.search(p, line) for p in PASSWORD_PATTERNS)


def find_command_prompt_current(chunk: str, vendor: str = "generic") -> str | None:
    """Ищет командный промпт в последней непустой строке.

    Возвращает matched prompt или None.
    """
    line = _last_nonempty_line(chunk)
    patterns = COMMAND_PROMPTS.get(vendor, COMMAND_PROMPTS["generic"])
    for pattern in patterns:
        match = re.search(pattern, line)
        if match:
            return match.group(0).strip()
    return None


def contains_login_failed(transcript: str) -> bool:
    """Ищет признаки неудачного логина по всему transcript."""
    return any(re.search(p, transcript) for p in LOGIN_FAILED_PATTERNS)


def contains_auth_retry(chunk: str) -> bool:
    """Ищет ELTEX-like экран retry после неудачной авторизации."""
    return any(re.search(p, chunk) for p in AUTH_RETRY_PATTERNS)


def parse_auth_lockout_seconds(text: str) -> int | None:
    """Вернуть длительность auth-lockout, если устройство её сообщило."""
    for pattern in AUTH_LOCKOUT_PATTERNS:
        match = re.search(pattern, text)
        if match and match.lastindex:
            return int(match.group(1))
    if any(re.search(pattern, text) for pattern in AUTH_LOCKOUT_PATTERNS):
        return 60
    return None


def contains_auth_lockout(text: str) -> bool:
    """Ищет блокировку CLI после превышения числа попыток входа."""
    return parse_auth_lockout_seconds(text) is not None


# --- Совместимость со старыми тестами ---

def match_login_prompt(text: str) -> bool:
    """Legacy: поиск login prompt по всему тексту (для тестов/диагностики)."""
    return match_login_current(text)


def match_password_prompt(text: str) -> bool:
    """Legacy: поиск password prompt по всему тексту."""
    return match_password_current(text)


def match_login_failed(text: str) -> bool:
    """Legacy alias для contains_login_failed."""
    return contains_login_failed(text)


def find_command_prompt(text: str, vendor: str = "generic") -> str | None:
    """Поиск промпта — сначала в последней строке, потом по всему тексту."""
    # Сначала проверяем последнюю строку (canonical)
    result = find_command_prompt_current(text, vendor)
    if result:
        return result
    # Fallback — поиск по всему тексту (для edge cases с доп. whitespace)
    patterns = COMMAND_PROMPTS.get(vendor, COMMAND_PROMPTS["generic"])
    for pattern in patterns:
        match = re.search(pattern, text, re.MULTILINE)
        if match:
            return match.group(0).strip()
    return None
