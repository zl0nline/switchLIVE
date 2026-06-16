"""Базовый интерфейс сессии CLI."""

from __future__ import annotations

import abc

from switchlive.core.credentials import Credentials
from switchlive.core.models import CommandResult


class DeviceSession(abc.ABC):
    """Интерактивная CLI-сессия поверх транспорта."""

    @abc.abstractmethod
    def login(self, credentials: Credentials) -> bool:
        """Войти на устройство. True при успехе."""

    @abc.abstractmethod
    def run_command(self, command: str, timeout: float = 10.0) -> CommandResult:
        """Выполнить команду и вернуть результат."""

    @abc.abstractmethod
    def is_ready(self) -> bool:
        """Сессия готова к выполнению команд."""
