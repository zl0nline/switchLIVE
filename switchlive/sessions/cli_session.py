"""Интерактивная CLI-сессия поверх serial/SSH транспорта."""

from __future__ import annotations

import logging
import time

from switchlive.core.credentials import Credentials
from switchlive.core.errors import SessionError
from switchlive.core.models import CommandResult
from switchlive.sessions.base import DeviceSession
from switchlive.sessions.pager import detect_pager, pager_response
from switchlive.sessions.prompts import (
    match_command_prompt,
    match_login_prompt,
    match_password_prompt,
)
from switchlive.transports.base import CommandTransport

log = logging.getLogger(__name__)


class CLISession(DeviceSession):
    """Сессия: логин, промпт, выполнение команд, paging."""

    def __init__(
        self,
        transport: CommandTransport,
        vendor: str = "generic",
        prompt_timeout: float = 5.0,
        command_timeout: float = 10.0,
    ) -> None:
        self.transport = transport
        self.vendor = vendor
        self.prompt_timeout = prompt_timeout
        self.command_timeout = command_timeout
        self._prompt: str | None = None

    def login(self, credentials: Credentials) -> bool:
        """Попробовать войти. Возвращает True при успехе."""
        try:
            # Сброс — отправить Enter
            self.transport.write(b"\r\n")
            output = self.transport.read_until_idle(self.prompt_timeout)

            text = output.decode(errors="replace")

            # Уже в командном режиме?
            prompt = match_command_prompt(text, self.vendor)
            if prompt:
                self._prompt = prompt
                log.debug("Already at command prompt: %s", prompt)
                return True

            # Логин?
            if match_login_prompt(text):
                self.transport.write(credentials.username.encode() + b"\r\n")
                output = self.transport.read_until_idle(self.prompt_timeout)
                text = output.decode(errors="replace")

            # Пароль?
            if match_password_prompt(text):
                self.transport.write(credentials.password.encode() + b"\r\n")
                output = self.transport.read_until_idle(self.prompt_timeout)
                text = output.decode(errors="replace")

            # Enable mode?
            if match_password_prompt(text):
                if credentials.enable_password:
                    self.transport.write(credentials.enable_password.encode() + b"\r\n")
                    output = self.transport.read_until_idle(self.prompt_timeout)
                    text = output.decode(errors="replace")
                else:
                    raise SessionError("Требуется enable password")

            prompt = match_command_prompt(text, self.vendor)
            if prompt:
                self._prompt = prompt
                log.info("Login successful, prompt: %s", prompt)
                return True

            raise SessionError(f"Не удалось определить промпт после логина. Вывод: {text[:200]}")

        except Exception as e:
            if isinstance(e, SessionError):
                raise
            raise SessionError(f"Ошибка при логине: {e}") from e

    def run_command(self, command: str, timeout: float | None = None) -> CommandResult:
        """Выполнить команду, обработать пейджер, собрать вывод."""
        if not self._prompt:
            raise SessionError("Сессия не готова: нет промпта")

        to = timeout or self.command_timeout

        # Отправить команду
        self.transport.write(command.encode() + b"\r\n")

        # Собрать вывод
        output = self.transport.read_until_idle(to)
        text = output.decode(errors="replace")

        # Обработка пейджера
        attempts = 0
        while detect_pager(text) and attempts < 50:
            self.transport.write(pager_response())
            time.sleep(0.3)
            more = self.transport.read_until_idle(to)
            text += more.decode(errors="replace")
            attempts += 1

        # Проверить промпт в конце
        prompt = match_command_prompt(text, self.vendor)
        if not prompt:
            log.warning("Команда завершена без промпта: %s", command[:50])

        return CommandResult(output=text, success=True)

    def is_ready(self) -> bool:
        return self._prompt is not None
