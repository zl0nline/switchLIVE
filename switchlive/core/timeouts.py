"""Динамические таймауты для тестового движка."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TimeoutPolicy:
    """Политика таймаутов с расширением."""

    base: float = 30.0
    poe: float = 180.0
    max: float = 600.0

    def for_port(self, supports_poe: bool = False) -> float:
        return self.poe if supports_poe else self.base

    def extend(self, current: float, reason: str = "") -> float:
        """Расширить таймаут при признаках прогресса."""
        new = current * 1.5
        return min(new, self.max)
