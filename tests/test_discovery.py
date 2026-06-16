"""Тесты device discovery (#5)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from switchlive.app.discovery import (
    _create_adapter,
    _try_login,
    run_discovery,
)
from switchlive.core.credentials import Credentials
from switchlive.core.models import DeviceIdentity
from switchlive.devices.dlink.adapter import DLinkAdapter
from switchlive.devices.dlink.detector import DLinkDetector
from switchlive.devices.registry import get_all_detectors, list_detector_vendors
from switchlive.sessions.cli_session import CLISession
from tests.test_transport import MockTransport


class TestDetectorRegistry:
    def test_dlink_detector_registered(self):
        vendors = list_detector_vendors()
        assert "dlink" in vendors

    def test_get_all_detectors(self):
        detectors = get_all_detectors()
        assert len(detectors) >= 1
        assert any(isinstance(d, DLinkDetector) for d in detectors)


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
        # Первая попытка (empty creds): видит Login, не может войти
        # Вторая попытка (standard): полный цикл
        transport = MockTransport()
        transport.add_response(b"Login: ")
        # username пустой → password prompt
        transport.add_response(b"Password: ")
        # password пустой → login failed
        transport.add_response(b"Login invalid\r\n")
        # Теперь standard login на новой "сессии" — но transport тот же
        # Нужно пересоздать session
        transport.add_response(b"Login: ")
        transport.add_response(b"Password: ")
        transport.add_response(b"switch:>")
        transport.open()

        session1 = CLISession(transport, vendor="dlink")
        creds = [Credentials(username="admin", password="admin")]

        def progress(msg):
            return None

        # Первая попытка с empty creds провалится
        try:
            session1.login(Credentials())
        except Exception:
            pass

        # Пересоздаём session для standard login
        session2 = CLISession(transport, vendor="dlink")
        result = _try_login(session2, creds, None, progress)
        assert result is not None

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


class TestRunDiscovery:
    def test_no_ports(self):
        """Нет COM-портов — ошибка."""
        with patch("switchlive.app.discovery.list_serial_ports", return_value=[]):
            result = run_discovery()
        assert result.found is False
        assert "COM-порт" in result.error

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
