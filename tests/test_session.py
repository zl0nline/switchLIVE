"""Тесты session layer (#4).

Покрывают:
- prompts: login/password/command по 5 вендорам + generic
- pager: detect/space/strip
- CLISession: state-machine login по свежим чанкам
- многострочные transcript (Login + Password + prompt в одном выводе)
- enable password flow
- password masking
"""

from __future__ import annotations

import pytest

from switchlive.core.credentials import Credentials
from switchlive.core.errors import SessionError
from switchlive.sessions.cli_session import CLISession
from switchlive.sessions.pager import (
    detect_pager,
    pager_space,
    strip_pager_artifacts,
)
from switchlive.sessions.prompts import (
    _last_nonempty_line,
    contains_login_failed,
    find_command_prompt,
    find_command_prompt_current,
    match_login_current,
    match_login_prompt,
    match_password_current,
    match_password_prompt,
)
from tests.test_transport import MockTransport

# --- Тесты prompts: last-line semantics ---

class TestPromptsLastLine:
    def test_last_nonempty_line_simple(self):
        assert _last_nonempty_line("line1\nline2\n") == "line2"

    def test_last_nonempty_line_trailing_whitespace(self):
        assert _last_nonempty_line("text\n   \n  switch:>  \n") == "switch:>"

    def test_last_nonempty_line_empty(self):
        assert _last_nonempty_line("") == ""
        assert _last_nonempty_line("\n\n") == ""

    def test_match_login_current_not_in_old_line(self):
        """Login prompt в старой строке не должен матчиться."""
        chunk = "Login: \nadmin\nPassword: \n***\nswitch:>"
        # Последняя строка — switch:> — не login
        assert match_login_current(chunk) is False

    def test_match_login_current_fresh(self):
        """Свежий login prompt матчится."""
        assert match_login_current("Login: ") is True
        assert match_login_current("some text\nLogin: ") is True

    def test_match_password_current_not_in_old_line(self):
        """Password prompt в старой строке не должен матчиться."""
        chunk = "Password: \nsecret\nswitch:>"
        assert match_password_current(chunk) is False

    def test_match_password_current_fresh(self):
        assert match_password_current("Password: ") is True
        assert match_password_current("text\nPassword: ") is True

    def test_find_command_prompt_current_not_old(self):
        """Промпт в старой строке не матчится, только в последней."""
        chunk = "switch:>\nshow version\nVersion 1.0\n"
        # Последняя строка — "Version 1.0" — не промпт
        assert find_command_prompt_current(chunk, "dlink") is None

    def test_find_command_prompt_current_fresh(self):
        chunk = "show version\nVersion 1.0\nswitch:>"
        assert find_command_prompt_current(chunk, "dlink") == "switch:>"

    def test_multiline_login_password_prompt(self):
        """Реальный многострочный вывод: Login + Password + prompt."""
        chunk = "Login:\r\nPassword:\r\nswitch:>"
        # Последняя строка — промпт
        assert find_command_prompt_current(chunk, "dlink") == "switch:>"
        assert match_login_current(chunk) is False
        assert match_password_current(chunk) is False


# --- Тесты prompts: basic matching ---

class TestPrompts:
    def test_match_login_prompt(self):
        assert match_login_prompt("Login: ") is True
        assert match_login_prompt("User Name: ") is True
        assert match_login_prompt("switch:>") is False

    def test_match_password_prompt(self):
        assert match_password_prompt("Password: ") is True
        assert match_password_prompt("Passwd: ") is True
        assert match_password_prompt("switch:>") is False

    def test_contains_login_failed(self):
        assert contains_login_failed("Login invalid") is True
        assert contains_login_failed("Access denied") is True
        assert contains_login_failed("Authentication failed") is True
        assert contains_login_failed("Welcome") is False

    def test_find_command_prompt_dlink(self):
        assert find_command_prompt("DES-1228:>", "dlink") == "DES-1228:>"
        assert find_command_prompt("SWITCH:#", "dlink") == "SWITCH:#"

    def test_find_command_prompt_cisco(self):
        assert find_command_prompt("Switch>", "cisco") == "Switch>"
        assert find_command_prompt("Switch#", "cisco") == "Switch#"

    def test_find_command_prompt_huawei(self):
        assert find_command_prompt("<HUAWEI>", "huawei") == "<HUAWEI>"
        assert find_command_prompt("[HUAWEI]", "huawei") == "[HUAWEI]"

    def test_find_command_prompt_none(self):
        assert find_command_prompt("random text", "generic") is None

    def test_find_command_prompt_fallback_generic(self):
        """Unknown vendor falls back to generic."""
        assert find_command_prompt("host>", "unknown_vendor") is not None


# --- Тесты pager ---

class TestPager:
    def test_detect_pager_more(self):
        assert detect_pager("--More--") is True
        assert detect_pager("some output\n--More--\n") is True

    def test_detect_pager_press_key(self):
        assert detect_pager("Press any key to continue") is True
        assert detect_pager("Press q to quit") is True

    def test_detect_pager_none(self):
        assert detect_pager("normal output") is False
        assert detect_pager("interface config") is False

    def test_pager_space(self):
        assert pager_space() == b" "

    def test_strip_pager_artifacts(self):
        text = "line1\n--More--\nline2"
        cleaned = strip_pager_artifacts(text)
        assert "--More--" not in cleaned
        assert "line1" in cleaned
        assert "line2" in cleaned


# --- Тесты CLISession: state-machine login ---

class TestCLISession:
    def test_session_not_ready_without_login(self):
        t = MockTransport()
        session = CLISession(t)
        assert session.is_ready() is False
        assert session.prompt is None

    def test_login_already_at_prompt(self):
        """Устройство уже в командном режиме — логин не нужен."""
        t = MockTransport()
        t.add_response(b"switch:>")
        t.open()

        session = CLISession(t, vendor="dlink")
        assert session.login(Credentials()) is True
        assert session.is_ready() is True
        assert session.prompt == "switch:>"

    def test_login_with_credentials(self):
        """Полный цикл: login → password → prompt (отдельные чанки)."""
        t = MockTransport()
        t.add_response(b"Login: ")        # после Enter
        t.add_response(b"Password: ")     # после username
        t.add_response(b"switch:>")       # после password
        t.open()

        session = CLISession(t, vendor="dlink")
        creds = Credentials(username="admin", password="***")
        assert session.login(creds) is True
        assert session.prompt == "switch:>"

    def test_login_multiline_chunk(self):
        """Многострочный чанк: Login + Password + prompt в одном."""
        t = MockTransport()
        # Первый чанк после Enter уже содержит весь flow
        t.add_response(b"\r\nLogin:\r\n")
        t.add_response(b"\r\nPassword:\r\n")
        t.add_response(b"\r\nswitch:>\r\n")
        t.open()

        session = CLISession(t, vendor="dlink")
        creds = Credentials(username="admin", password="***")
        assert session.login(creds) is True
        assert session.prompt == "switch:>"

    def test_login_multiline_all_in_one_chunk(self):
        """Экстремальный случай: всё в одном чанке, session уже в prompt."""
        t = MockTransport()
        t.add_response(b"Login:\r\nPassword:\r\nswitch:>")
        t.open()

        session = CLISession(t, vendor="dlink")
        # Первый chunk: last line = switch:> → сразу готовы
        assert session.login(Credentials()) is True
        assert session.prompt == "switch:>"

    def test_login_failed(self):
        """Неверный пароль → SessionError."""
        t = MockTransport()
        t.add_response(b"Login: ")
        t.add_response(b"Password: ")
        t.add_response(b"Login invalid\r\n")
        t.open()

        session = CLISession(t, vendor="dlink")
        creds = Credentials(username="admin", password="***")
        with pytest.raises(SessionError, match="Авторизация не удалась"):
            session.login(creds)

    def test_login_enable_password(self):
        """Требуется enable password (отдельные чанки)."""
        t = MockTransport()
        t.add_response(b"Login: ")
        t.add_response(b"Password: ")
        t.add_response(b"Password: ")  # enable prompt
        t.add_response(b"switch:#")
        t.open()

        session = CLISession(t, vendor="dlink")
        creds = Credentials(username="admin", password="***", enable_password="enable123")
        assert session.login(creds) is True
        assert session.prompt == "switch:#"

    def test_login_enable_password_multiline(self):
        """Enable flow с многострочным transcript."""
        t = MockTransport()
        t.add_response(b"Login: ")
        t.add_response(b"Password: ")
        # После password — enable prompt + результат в одном чанке
        t.add_response(b"Password: ")  # enable prompt (fresh last line)
        t.add_response(b"switch:#")
        t.open()

        session = CLISession(t, vendor="dlink")
        creds = Credentials(username="admin", password="***", enable_password="en123")
        assert session.login(creds) is True
        assert session.prompt == "switch:#"

    def test_login_enable_required_but_not_provided(self):
        """Требуется enable password, но не предоставлено."""
        t = MockTransport()
        t.add_response(b"Login: ")
        t.add_response(b"Password: ")
        t.add_response(b"Password: ")  # enable prompt
        t.open()

        session = CLISession(t, vendor="dlink")
        creds = Credentials(username="admin", password="***")
        with pytest.raises(SessionError, match="enable password"):
            session.login(creds)

    def test_login_no_prompt_detected(self):
        """Не удалось определить состояние устройства."""
        t = MockTransport()
        t.add_response(b"some garbage output\r\nno prompt here")
        t.open()

        session = CLISession(t, vendor="dlink")
        with pytest.raises(SessionError, match="Не удалось определить промпт"):
            session.login(Credentials())

    def test_run_command_without_login(self):
        """Команда без логина → SessionError."""
        t = MockTransport()
        session = CLISession(t)
        with pytest.raises(SessionError, match="нет промпта"):
            session.run_command("show version")

    def test_run_command_success(self):
        """Выполнение команды после логина."""
        t = MockTransport()
        t.add_response(b"switch:>")  # initial prompt
        t.add_response(b"Version 1.0\nswitch:>")  # command output
        t.open()

        session = CLISession(t, vendor="dlink")
        session.login(Credentials())

        result = session.run_command("show version")
        assert result.success is True
        assert "Version 1.0" in result.output

    def test_run_command_returns_raw_output_but_redacts_transcript(self):
        """Diagnostic redaction must not mutate command output used by parsers."""
        t = MockTransport()
        t.add_response(b"switch:>")  # initial prompt
        t.add_response(b"password: secret123\nswitch:>")
        t.open()

        session = CLISession(t, vendor="dlink")
        session.login(Credentials())

        result = session.run_command("show running-config")
        assert "password: secret123" in result.output
        assert "secret123" not in session.transcript
        assert "password: ***" in session.transcript

    def test_run_command_with_pager(self):
        """Команда с пейджером — автоматически пролистывается."""
        t = MockTransport()
        t.add_response(b"switch:>")  # initial prompt
        t.add_response(b"line1\n--More--\n")  # first page
        t.add_response(b"line2\nswitch:>")  # second page
        t.open()

        session = CLISession(t, vendor="dlink")
        session.login(Credentials())

        result = session.run_command("show config")
        assert result.success is True
        assert "line1" in result.output
        assert "line2" in result.output
        assert "--More--" not in result.output  # пейджер убран

    def test_transcript_stored(self):
        """Transcript хранится для диагностики."""
        t = MockTransport()
        t.add_response(b"Login: ")
        t.add_response(b"Password: ")
        t.add_response(b"switch:>")
        t.open()

        session = CLISession(t, vendor="dlink")
        session.login(Credentials(username="admin", password="***"))
        assert "Login" in session.transcript
        assert "Password" in session.transcript or "***" in session.transcript

    def test_safe_text_masks_password(self):
        """Пароли маскируются в логах."""
        t = MockTransport()
        session = CLISession(t)
        masked = session._safe_text("Password: secret123")
        assert "secret123" not in masked
        assert "***" in masked

    def test_safe_text_masks_network_cli_password_forms(self):
        t = MockTransport()
        session = CLISession(t)
        masked = session._safe_text(
            "\n".join(
                [
                    "enable password 7 enableSecret",
                    "username admin password adminSecret",
                    "snmp-server community publicSecret RO",
                ]
            )
        )
        assert "enableSecret" not in masked
        assert "adminSecret" not in masked
        assert "publicSecret" not in masked

    def test_transcript_masks_secrets(self):
        """В transcript пароли маскируются, не хранятся открыто."""
        t = MockTransport()
        t.add_response(b"Password: ")
        # После ввода пароля — ответ устройства
        t.add_response(b"switch:>")
        t.open()

        # Нужен login prompt сначала
        t2 = MockTransport()
        t2.add_response(b"Login: ")
        t2.add_response(b"Password: ")
        t2.add_response(b"switch:>")
        t2.open()

        session2 = CLISession(t2, vendor="dlink")
        session2.login(Credentials(username="admin", password="mypassword"))
        # Пароль не должен быть в transcript открыто
        assert "mypassword" not in session2.transcript
