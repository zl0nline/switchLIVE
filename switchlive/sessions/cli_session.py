"""Интерактивная CLI-сессия поверх serial/SSH транспорта.

Login flow — state-machine по свежему output chunk:
  INIT → (send newline) → читаем chunk
  → LOGIN_PROMPT? → отправляем username → читаем chunk
  → PASSWORD_PROMPT? → отправляем password → читаем chunk
  → COMMAND_PROMPT? → готово
  → PASSWORD_PROMPT снова? → enable password → читаем chunk
  → COMMAND_PROMPT? → готово
  → LOGIN_FAILED? → SessionError

Важно: на каждом шаге смотрим только свежий chunk (последнюю строку),
а не весь накопленный transcript. Transcript хранится отдельно для диагностики.
"""

from __future__ import annotations

import logging
import time

from switchlive.core.credentials import Credentials
from switchlive.core.errors import SessionError
from switchlive.core.models import CommandResult
from switchlive.diagnostics import redact_text
from switchlive.sessions.base import DeviceSession
from switchlive.sessions.pager import (
    detect_pager,
    pager_space,
    strip_pager_artifacts,
)
from switchlive.sessions.prompts import (
    contains_login_failed,
    find_command_prompt_current,
    match_login_current,
    match_password_current,
)
from switchlive.transports.base import CommandTransport

log = logging.getLogger(__name__)

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
        self._username: str = ""
        self._transcript: str = ""  # полный лог сессии (для диагностики)

    @property
    def prompt(self) -> str | None:
        return self._prompt

    @property
    def transcript(self) -> str:
        """Полный вывод сессии — для диагностики."""
        return self._transcript

    def login(self, credentials: Credentials) -> bool:
        """State-machine логин по свежим чанкам вывода.

        Returns True при успехе.
        Raises SessionError при невозможности войти.
        """
        self._username = credentials.username
        self._transcript = ""

        try:
            # Шаг 1: «подёргать» — отправить Enter, получить первый чанк
            chunk = self._send_and_read(b"\r\n", self.prompt_timeout)

            # Уже в командном режиме?
            prompt = find_command_prompt_current(chunk, self.vendor)
            if prompt:
                self._prompt = prompt
                log.info("Already at command prompt: %s", prompt)
                return True

            # Шаг 2: login prompt?
            if match_login_current(chunk):
                chunk = self._send_and_read(
                    credentials.username.encode() + b"\r\n",
                    self.prompt_timeout,
                )
            # Шаг 3: password prompt?
            if match_password_current(chunk):
                chunk = self._send_secret_and_read(
                    credentials.password,
                    self.prompt_timeout,
                )

            # Проверить login failed
            if contains_login_failed(self._transcript):
                raise SessionError(
                    f"Авторизация не удалась (пользователь: {credentials.username})"
                )

            # Уже командный промпт?
            prompt = find_command_prompt_current(chunk, self.vendor)
            if prompt:
                self._prompt = prompt
                log.info(
                    "Login successful: user=%s prompt=%s",
                    credentials.username,
                    prompt,
                )
                return True

            # Шаг 4: enable password prompt?
            if match_password_current(chunk):
                if credentials.enable_password:
                    chunk = self._send_secret_and_read(
                        credentials.enable_password,
                        self.prompt_timeout,
                    )
                else:
                    raise SessionError("Требуется enable password")

            # Финальная проверка промпта
            prompt = find_command_prompt_current(chunk, self.vendor)
            if prompt:
                self._prompt = prompt
                log.info(
                    "Login successful (enable): user=%s prompt=%s",
                    credentials.username,
                    prompt,
                )
                return True

            # Login failed после enable?
            if contains_login_failed(self._transcript):
                raise SessionError(
                    f"Авторизация не удалась (пользователь: {credentials.username})"
                )

            if match_password_current(chunk):
                raise SessionError("Не удалось войти — возможно неверный пароль")

            raise SessionError(
                f"Не удалось определить промпт после логина. "
                f"Последний вывод: {self._safe_text(chunk)[:200]}"
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
        chunk = self._send_and_read(
            command.encode() + b"\r\n", to
        )

        # Обработка пейджера
        iterations = 0
        while detect_pager(chunk) and iterations < MAX_PAGER_ITERATIONS:
            more = self._send_and_read(pager_space(), to)
            if not more.strip():
                break
            chunk += more
            iterations += 1

        if iterations >= MAX_PAGER_ITERATIONS:
            log.warning(
                "Pager iterations limit reached for command: %s",
                command[:50],
            )

        # Очистить артефакты пейджера
        chunk = strip_pager_artifacts(chunk)

        # Проверить промпт в конце
        prompt = find_command_prompt_current(chunk, self.vendor)
        if not prompt:
            log.warning(
                "Command completed without prompt: %s",
                command[:50],
            )

        return CommandResult(output=chunk, success=True)

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

    def _send_and_read(self, data: bytes, timeout: float) -> str:
        """Отправить байты, прочитать ответ, добавить в transcript, вернуть chunk."""
        log.debug("TX: %s", self._safe_bytes(data))
        self.transport.write(data)
        time.sleep(0.1)
        raw = self.transport.read_until_idle(timeout)
        chunk = raw.decode(errors="replace")
        safe_chunk = self._safe_text(chunk)
        self._transcript += safe_chunk
        log.debug("RX: %s", safe_chunk)
        return chunk

    def _send_secret_and_read(self, secret: str, timeout: float) -> str:
        """Отправить пароль (без попадания в логи), прочитать ответ."""
        log.debug("TX: ***")
        self.transport.write(secret.encode() + b"\r\n")
        time.sleep(0.3)
        raw = self.transport.read_until_idle(timeout)
        chunk = raw.decode(errors="replace")
        # В transcript пишем маскированную версию
        safe_chunk = self._safe_text(chunk)
        self._transcript += safe_chunk
        log.debug("RX: %s", safe_chunk)
        return chunk

    def _safe_text(self, text: str) -> str:
        """Маскировать потенциальные пароли в тексте для логов."""
        return redact_text(text)

    def _safe_bytes(self, data: bytes) -> str:
        """Decode command bytes for debug logs without control noise."""
        text = data.decode(errors="replace").replace("\r", "\\r").replace("\n", "\\n")
        return self._safe_text(text)
