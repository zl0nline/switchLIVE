"""Тесты device discovery (#5)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from switchlive.app.discovery import (
    DiscoveryResult,
    _create_adapter,
    _has_auth_console_output,
    _try_baudrate,
    _try_login,
    _try_port,
    run_discovery,
)
from switchlive.core.credentials import Credentials
from switchlive.core.models import DeviceIdentity
from switchlive.devices.dlink.adapter import DLinkAdapter
from switchlive.devices.dlink.detector import DLinkDetector
from switchlive.devices.eltex.adapter import EltexAdapter
from switchlive.devices.eltex.detector import EltexDetector
from switchlive.devices.registry import get_all_detectors, list_detector_vendors
from switchlive.sessions.cli_session import CLISession
from tests.test_transport import MockTransport


class TestDetectorRegistry:
    def test_dlink_detector_registered(self):
        vendors = list_detector_vendors()
        assert "dlink" in vendors

    def test_eltex_detector_registered(self):
        vendors = list_detector_vendors()
        assert "eltex" in vendors

    def test_get_all_detectors(self):
        detectors = get_all_detectors()
        assert len(detectors) >= 1
        assert any(isinstance(d, DLinkDetector) for d in detectors)
        assert any(isinstance(d, EltexDetector) for d in detectors)


class TestDLinkDetector:
    def test_can_detect_dlink(self):
        """Детектор распознаёт D-Link вывод."""
        transport = MockTransport()
        transport.add_response(b"DES-1228:>")  # initial prompt
        transport.add_response(
            b"Device Type: DES-1228\nFirmware Version: 2.00.B01\nDES-1228:>"
        )
        transport.open()

        session = CLISession(transport, vendor="dlink")
        session.login(Credentials())

        detector = DLinkDetector()
        assert detector.can_detect(session) is True

    def test_can_detect_not_dlink(self):
        """Детектор не распознаёт чужой вывод."""
        transport = MockTransport()
        transport.add_response(b"router>")
        transport.add_response(b"some router output\nrouter>")
        transport.open()

        session = CLISession(transport, vendor="generic")
        session.login(Credentials())

        detector = DLinkDetector()
        assert detector.can_detect(session) is False

    def test_identify(self):
        """Полная идентификация D-Link."""
        transport = MockTransport()
        transport.add_response(b"switch:>")
        transport.add_response(
            b"Device Type: DES-1228\n"
            b"Hardware Version: A1\n"
            b"Firmware Version: 2.00.B01\n"
            b"Serial Number: PZA00AB00001\n"
            b"switch:>"
        )
        transport.open()

        session = CLISession(transport, vendor="dlink")
        session.login(Credentials())

        detector = DLinkDetector()
        identity = detector.identify(session)
        assert identity.vendor == "D-Link"
        assert identity.model == "DES-1228"
        assert identity.serial == "PZA00AB00001"
        assert identity.firmware == "2.00.B01"


class TestCreateAdapter:
    def test_create_dlink_adapter(self):
        ident = DeviceIdentity(vendor="D-Link", model="DES-1228")
        adapter = _create_adapter(ident)
        assert isinstance(adapter, DLinkAdapter)
        assert adapter.profile.model == "DES-1228"

    def test_create_eltex_adapter(self):
        ident = DeviceIdentity(vendor="Eltex", model="MES2324FB")
        adapter = _create_adapter(ident)
        assert isinstance(adapter, EltexAdapter)
        assert adapter.profile.model == "MES2324FB"

    def test_create_unknown_vendor(self):
        ident = DeviceIdentity(vendor="Unknown", model="XYZ")
        adapter = _create_adapter(ident)
        # Fallback — не падает
        assert adapter is not None


class TestTryLogin:
    def test_login_none_required(self):
        transport = MockTransport()
        transport.add_response(b"switch:>")
        transport.open()

        session = CLISession(transport, vendor="dlink")
        def progress(msg):
            return None
        result = _try_login(session, [], None, progress)
        assert result == "none"

    def test_login_standard(self):
        # _try_login с standard_creds:
        # 1. else-branch: _read_buffered -> empty -> send \r -> switch shows Login:
        # 2. match_login_current -> True -> session._at_login_prompt = True
        # 3. login(admin): _at_login_prompt -> send admin directly -> Password: -> pass -> prompt
        transport = MockTransport()
        transport.add_response(b"")  # _read_buffered in else-branch
        transport.add_response(b"Login: ")  # _send_and_read(b"\r") in else-branch
        transport.add_response(b"Password: ")  # login sends admin directly
        transport.add_response(b"switch:>")  # login sends password
        transport.open()

        session = CLISession(transport, vendor="dlink")
        creds = [Credentials(username="admin", password="admin")]

        def progress(msg):
            return None

        result = _try_login(session, creds, None, progress)
        assert result is not None
        assert result == "standard"

    def test_login_manual(self):
        transport = MockTransport()
        # empty creds fail
        transport.add_response(b"Login: ")
        transport.add_response(b"Password: ")
        transport.add_response(b"Login invalid\r\n")
        # manual login
        transport.add_response(b"Login: ")
        transport.add_response(b"Password: ")
        transport.add_response(b"switch:>")
        transport.open()

        session1 = CLISession(transport, vendor="dlink")

        def callback(creds):
            return Credentials(username="operator", password="op123")

        def progress(msg):
            return None

        try:
            session1.login(Credentials())
        except Exception:
            pass

        session2 = CLISession(transport, vendor="dlink")
        result = _try_login(session2, [], callback, progress)
        assert result is not None

    def test_login_failed_all(self):
        """Все попытки входа провалились."""
        transport = MockTransport()
        transport.add_response(b"Login: ")
        transport.add_response(b"Password: ")
        transport.add_response(b"Login invalid")
        transport.open()

        session = CLISession(transport, vendor="dlink")
        def progress(msg):
            return None
        result = _try_login(session, [], None, progress)
        assert result is None

    def test_login_lockout_is_reported(self):
        """CLI lockout must stop retries and be visible to the operator."""
        transport = MockTransport()
        # else-branch: _read_buffered -> empty, _send_and_read(\r) -> UserName:
        transport.add_response(b"")
        transport.add_response(b"UserName:")  # wake -> login prompt
        # _at_login_prompt=True, login(admin): send admin directly
        transport.add_response(b"PassWord:")  # admin -> PassWord:
        # send password -> lockout
        transport.add_response(
            b"Fail!\n\nBlocked unauthorized CLI access!\n"
            b"Maximum number of login attempts reached. Lock out for 60 seconds.\n"
        )
        transport.open()

        messages = []

        with patch("switchlive.app.discovery.SerialTransport", return_value=transport):
            result, had_output = _try_baudrate(
                "/dev/ttyUSB0",
                115200,
                [Credentials(username="admin", password="admin")],
                manual_callback=None,
                detectors=[],
                progress=messages.append,
            )

        assert had_output is True
        assert result is not None
        assert result.found is False
        assert "Подождите 60 секунд" in result.error
        assert any("Блокировка авторизации" in msg for msg in messages)


class TestRunDiscovery:
    def test_no_ports(self):
        """Нет COM-портов — ошибка."""
        with patch("switchlive.app.discovery.list_serial_ports", return_value=[]):
            with patch("switchlive.app.discovery.is_pyserial_available", return_value=True):
                result = run_discovery()
        assert result.found is False
        assert "COM-порт" in result.error

    def test_no_pyserial(self):
        """Нет pyserial в текущем Python — понятная ошибка."""
        with patch("switchlive.app.discovery.list_serial_ports", return_value=[]):
            with patch("switchlive.app.discovery.is_pyserial_available", return_value=False):
                result = run_discovery()
        assert result.found is False
        assert "pyserial" in result.error
        assert "sudo" in result.error

    def test_no_ports_progress_reports_pyserial(self):
        messages = []
        with patch("switchlive.app.discovery.list_serial_ports", return_value=[]):
            with patch("switchlive.app.discovery.is_pyserial_available", return_value=False):
                result = run_discovery(progress_callback=messages.append)
        assert result.found is False
        assert any("pyserial" in message for message in messages)

    def test_has_auth_console_output_accepts_eltex_retry(self):
        assert _has_auth_console_output(
            "\r\nUser Name:\r\n"
            "\r\nauthentication failed\r\n"
            "\r\npress ENTER key to retry authentication\r\n"
        ) is True

    def test_has_auth_console_output_rejects_garbled_baudrate(self):
        assert _has_auth_console_output("garbage bytes") is False

    def test_dead_switch_no_output_suggests_reboot(self):
        """Если коммутатор вообще не отвечает — подсказка про перезагрузку."""
        mock_port = MagicMock()
        mock_port.name = "/dev/ttyUSB0"

        with patch("switchlive.app.discovery.list_serial_ports", return_value=[mock_port]):
            with patch("switchlive.app.discovery._try_port", return_value=(None, False)):
                result = run_discovery(
                    standard_logins_path="nonexistent.txt",
                    silent_retries=0,
                )

        assert result.found is False
        assert result.error is not None
        assert "перезагрузить" in result.error.lower() or "не работает" in result.error.lower()

    def test_silent_console_retry_can_find_after_reboot_wait(self):
        """После reboot console может молчать; discovery должен повторить попытку."""
        mock_port = MagicMock()
        mock_port.name = "/dev/ttyUSB0"
        found = DiscoveryResult(found=True)

        with patch("switchlive.app.discovery.list_serial_ports", return_value=[mock_port]):
            with patch(
                "switchlive.app.discovery._try_port",
                side_effect=[(None, False), (found, True)],
            ):
                with patch("switchlive.app.discovery.time.sleep") as sleep:
                    result = run_discovery(
                        standard_logins_path="nonexistent.txt",
                        silent_retries=1,
                        silent_retry_delay=0.1,
                    )

        assert result is found
        sleep.assert_called_once_with(0.1)

    def test_found_on_first_port(self):
        """Устройство найдено — интеграционный тест через mock transport."""
        mock_port = MagicMock()
        mock_port.name = "/dev/ttyUSB0"

        transport = MockTransport()
        # Session wake-up: already at prompt
        transport.add_response(b"DES-1228:>")
        # disable clipaging response
        transport.add_response(b"DES-1228:>")
        # can_detect: show switch #1
        transport.add_response(
            b"Device Type: DES-1228\n"
            b"DES-1228:>"
        )
        # identify: show switch #2
        transport.add_response(
            b"Device Type: DES-1228\n"
            b"Firmware Version: 2.00.B01\n"
            b"Serial Number: SN001\n"
            b"DES-1228:>"
        )
        transport.open()

        with patch("switchlive.app.discovery.list_serial_ports", return_value=[mock_port]):
            with patch(
                "switchlive.app.discovery.SerialTransport",
                return_value=transport,
            ):
                result = run_discovery(standard_logins_path="nonexistent.txt")

        assert result.found is True
        assert result.identity is not None
        assert result.identity.model == "DES-1228"

    def test_try_port_checks_all_baudrates_before_manual_login(self):
        manual_callback = MagicMock()
        detector = MagicMock()
        found = DiscoveryResult(found=True)
        calls = []

        def fake_try_baudrate(*args, **kwargs):
            calls.append(kwargs["manual_callback"])
            if len(calls) == 1:
                return None, True
            return found, True

        with patch("switchlive.app.discovery._try_baudrate", side_effect=fake_try_baudrate):
            result, _ = _try_port("/dev/ttyUSB0", [], manual_callback, [detector], lambda msg: None)

        assert result is found
        assert calls == [None, None]
        manual_callback.assert_not_called()

    def test_try_port_uses_configured_baudrates(self):
        manual_callback = MagicMock()
        detector = MagicMock()
        checked_baudrates = []

        def fake_try_baudrate(*args, **kwargs):
            checked_baudrates.append(args[1])
            return None, False

        with patch("switchlive.app.discovery._try_baudrate", side_effect=fake_try_baudrate):
            result, had_output = _try_port(
                "/dev/ttyUSB0",
                [],
                manual_callback,
                [detector],
                lambda msg: None,
                baudrates=(115200, 9600, 57600),
            )

        assert result is None
        assert had_output is False
        assert checked_baudrates == [115200, 9600, 57600]

    def test_try_port_defers_manual_login_until_auto_baudrates_fail(self):
        manual_callback = MagicMock()
        detector = MagicMock()
        calls = []

        def fake_try_baudrate(*args, **kwargs):
            calls.append(kwargs["manual_callback"])
            return None, True

        with patch("switchlive.app.discovery._try_baudrate", side_effect=fake_try_baudrate):
            result, _ = _try_port("/dev/ttyUSB0", [], manual_callback, [detector], lambda msg: None)

        assert result is None
        assert calls == [None, None, manual_callback, manual_callback]
