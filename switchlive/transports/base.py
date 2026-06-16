"""Базовый интерфейс транспорта."""

from __future__ import annotations

import abc


class CommandTransport(abc.ABC):
    """Транспорт: соединение с устройством на уровне байтов."""

    @abc.abstractmethod
    def open(self) -> None:
        """Установить соединение."""

    @abc.abstractmethod
    def close(self) -> None:
        """Закрыть соединение."""

    @abc.abstractmethod
    def write(self, data: bytes) -> None:
        """Отправить байты."""

    @abc.abstractmethod
    def read_until_idle(self, timeout: float) -> bytes:
        """Читать до наступления «тишины» в канале."""

    @abc.abstractmethod
    def is_open(self) -> bool:
        """Соединение активно."""
