"""Базовые классы ошибок и исключений."""


class SwitchLiveError(Exception):
    """Базовая ошибка switchLIVE."""


class TransportError(SwitchLiveError):
    """Ошибка транспортного уровня."""


class SessionError(SwitchLiveError):
    """Ошибка сессии (логин, промпт, paging)."""


class AuthLockoutError(SessionError):
    """Консоль временно заблокировала авторизацию после неудачных попыток."""

    def __init__(self, message: str, retry_after_seconds: int | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class DeviceError(SwitchLiveError):
    """Ошибка устройства."""


class TestError(SwitchLiveError):
    """Ошибка тестового движка."""
