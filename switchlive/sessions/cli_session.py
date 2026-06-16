"""Интерактивная CLI-сессия поверх serial/SSH транспорта.

Сессия знает про:
- логин (login/password/enable)
- промпты (определение командного режима)
- пейджеры (--More--)
- маскировку паролей в логах

Не знает про:
- конкретные команды (show version, и т.д.) — это DeviceAdapter
- тесты — это TestEngine
- формат отчётов — это ReportWriter
"""

from __future__ import annotations

import logging
import time

from switchlive.core.credentials import Credentials
from switchlive.core.errors import SessionError
from switchlive.core.models import CommandResult
from switchlive.sessions.base import DeviceSession
from switchlive.sessions.pager import (
    detect_pager,
    pager_space,
    strip_pager_artifacts,
)
from switchlive.sessions.prompts import (
    find_command_prompt,
    match_login_failed,
    match_login_prompt,
    match_password_prompt,
)
from switchlive.transports.base import CommandTransport

log = logging.getLogger(__name__)

# Лимит итераций пейджера — защита от зависания
MAX_PAGER_ITERATIONS = 100


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
        self._username: str = ""  # для логов (без пароля!)

    @property
    def prompt(self) -> str | None:
        return self._prompt

    def login(self, credentials: Credentials) -> bool:
        """Попробовать войти на устройство.

        Returns True при успехе.
        Raises SessionError при невозможности войти.
        """
        self._username = credentials.username

        try:
            # «Подёргать» устройство — отправить Enter
            self.transport.write(b"\r\n")
            time.sleep(0.5)
            output = self.transport.read_until_idle(self.prompt_timeout)
            text = output.decode(errors="replace")

            # Уже в командном режиме?
            prompt = find_command_prompt(text, self.vendor)
            if prompt:
                self._prompt = prompt
                log.info("Already at command prompt: %s", prompt)
                return True

            # Требуется логин?
            attempts = 0
            while match_login_prompt(text) and attempts < 3:
                self.transport.write(credentials.username.encode() + b"\r\n")
                time.sleep(0.3)
                output = self.transport.read_until_idle(self.prompt_timeout)
                text += output.decode(errors="replace")
                attempts += 1

            # Требуется пароль?
            if match_password_prompt(text):
                self._write_secret(credentials.password + "\r\n")
                time.sleep(0.5)
                output = self.transport.read_until_idle(self.prompt_timeout)
                text += output.decode(errors="replace")

            # Проверить login failed
            if match_login_failed(text):
                raise SessionError(
                    f"Авторизация не удалась (пользователь: {credentials.username})"
                )

            # Enable mode?
            if match_password_prompt(text):
                if credentials.enable_password:
                    self._write_secret(credentials.enable_password + "\r\n")
                    time.sleep(0.5)
                    output = self.transport.read_until_idle(self.prompt_timeout)
                    text += output.decode(errors="replace")
                else:
                    raise SessionError("Требуется enable password")

            # Проверить промпт
            prompt = find_command_prompt(text, self.vendor)
            if prompt:
                self._prompt = prompt
                log.info(
                    "Login successful: user=%s prompt=%s",
                    credentials.username,
                    prompt,
                )
                return True

            # Может ещё пароль просит?
            if match_password_prompt(text):
                raise SessionError("Не удалось войти — возможно неверный пароль")

            raise SessionError(
                f"Не удалось определить промпт после логина. "
                f"Последний вывод: {self._safe_text(text)[:200]}"
            )

        except SessionError:
            raise
        except Exception as e:
            raise SessionError(f"Ошибка при логине: {e}") from e

    def run_command(
        self, command: str, timeout: float | None = None
    ) -> CommandResult:
        """Выполнить команду, обработать пейджер, собрать вывод.

        Returns CommandResult с полным выводом.
        """
        if not self._prompt:
            raise SessionError("Сессия не готова: нет промпта")

        to = timeout or self.command_timeout

        # Отправить команду
        self.transport.write(command.encode() + b"\r\n")

        # Собрать вывод
        output = self.transport.read_until_idle(to)
        text = output.decode(errors="replace")

        # Обработка пейджера
        iterations = 0
        while detect_pager(text) and iterations < MAX_PAGER_ITERATIONS:
            self.transport.write(pager_space())
            time.sleep(0.3)
            more = self.transport.read_until_idle(to)
            if not more:
                break
            text += more.decode(errors="replace")
            iterations += 1

        if iterations >= MAX_PAGER_ITERATIONS:
            log.warning(
                "Pager iterations limit reached for command: %s",
                command[:50],
            )

        # Очистить артефакты пейджера
        text = strip_pager_artifacts(text)

        # Проверить промпт в конце
        prompt = find_command_prompt(text, self.vendor)
        if not prompt:
            log.warning(
                "Command completed without prompt: %s",
                command[:50],
            )

        return CommandResult(output=text, success=True)

    def disable_paging(self, command: str = "") -> None:
        """Отправить команду для отключения пейджера.

        Вендор-специфичная команда передаётся через аргумент.
        Например для D-Link: 'disable clipaging'
        """
        if command:
            self.run_command(command)

    def is_ready(self) -> bool:
        return self._prompt is not None

    # --- Внутренние методы ---

    def _write_secret(self, text: str) -> None:
        """Отправить секрет (пароль) без попадания в логи."""
        self.transport.write(text.encode())

    def _safe_text(self, text: str) -> str:
        """Маскировать потенциальные пароли в тексте для логов."""
        # Убираем строки с password
        import re

        return re.sub(
            r"(?i)(password\s*:?\s*)\S+",
            r"\1***",
            text,
        )
