"""Базовые классы ошибок и исключений."""


class SwitchLiveError(Exception):
    """Базовая ошибка switchLIVE."""


class TransportError(SwitchLiveError):
    """Ошибка транспортного уровня."""


class SessionError(SwitchLiveError):
    """Ошибка сессии (логин, промпт, paging)."""


class DeviceError(SwitchLiveError):
    """Ошибка устройства."""


class TestError(SwitchLiveError):
    """Ошибка тестового движка."""
