"""Интеграционные тесты: DLinkAdapter + WalkTestEngine (#7/#8/#9 fix).

Проверяем, что реальный adapter contract работает с новыми моделями.
Mock строго по DeviceAdapter interface — без кастомного shape.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from switchlive.app.walk_test import WalkTestEngine
from switchlive.core.models import MacEntry, PortInfo, PortType, PortVerdict


def _make_contract_adapter(ports, mac_entries=None, counters=None):
    """Mock строго по DeviceAdapter контракту."""
    adapter = MagicMock()
    adapter.list_ports.return_value = ports
    # get_mac_table возвращает list[MacEntry] по контракту
    adapter.get_mac_table.return_value = mac_entries or []
    adapter.get_counters.return_value = counters or {}
    adapter.shutdown_port.return_value = None
    adapter.get_poe_status.return_value = {}
    adapter.get_transceiver.return_value = {}
    return adapter


class TestDLinkAdapterCompatibility:
    """Проверка совместимости с реальным DLinkAdapter shape."""

    def test_dlink_profile_ports_have_type(self):
        """Порты из D-Link профилей имеют поле .type."""
        from switchlive.devices.dlink.profiles import DLinkDES12xx, DLinkDGS3420

        for profile_cls in [DLinkDES12xx, DLinkDGS3420]:
            p = profile_cls()
            for port in p.ports:
                assert hasattr(port, "type")
                assert isinstance(port.type, PortType)

    def test_dlink_adapter_get_mac_table_returns_macentry(self):
        """DLinkAdapter.get_mac_table возвращает list[MacEntry]."""
        from switchlive.devices.dlink.adapter import DLinkAdapter

        adapter = DLinkAdapter()
        session = MagicMock()
        session.run_command.return_value = MagicMock(output="""

        1       00-1A-2B-3C-4D-5E  5
        1       00-50-BA-12-34-56  1
        """)

        entries = adapter.get_mac_table(session)
        assert isinstance(entries, list)
        for e in entries:
            assert isinstance(e, MacEntry)
            assert hasattr(e, "mac")
            assert hasattr(e, "port_index")


class TestWalkTestWithContractAdapter:
    """Walk-test с mock строго по DeviceAdapter контракту."""

    def test_clean_port_pass(self):
        """Чистый порт → PASS через contract adapter."""
        ports = [PortInfo(index=1, name="1", type=PortType.COPPER)]
        mac_seq = [
            [],  # baseline
            [MacEntry(mac="AA:BB:CC:DD:EE:01", port_index=1)],
            [MacEntry(mac="AA:BB:CC:DD:EE:01", port_index=1)],
            [MacEntry(mac="AA:BB:CC:DD:EE:01", port_index=1)],
        ]
        adapter = _make_contract_adapter(
            ports=ports, mac_entries=None, counters={"crc": 0, "drops": 0}
        )
        adapter.get_mac_table.side_effect = mac_seq
        session = MagicMock()

        engine = WalkTestEngine(adapter, session)
        result = engine._test_port(ports[0], lambda s, m: None)

        assert result.verdict == PortVerdict.PASS

    def test_crc_port_warn(self):
        """Порт с CRC → WARN через contract adapter."""
        ports = [PortInfo(index=1, name="1", type=PortType.COPPER)]
        mac_seq = [
            [],
            [MacEntry(mac="AA:BB:CC:DD:EE:01", port_index=1)],
            [MacEntry(mac="AA:BB:CC:DD:EE:01", port_index=1)],
            [MacEntry(mac="AA:BB:CC:DD:EE:01", port_index=1)],
        ]
        adapter = _make_contract_adapter(
            ports=ports, counters={"crc": 10, "drops": 3}
        )
        adapter.get_mac_table.side_effect = mac_seq
        session = MagicMock()

        engine = WalkTestEngine(adapter, session)
        result = engine._test_port(ports[0], lambda s, m: None)

        assert result.verdict == PortVerdict.WARN

    def test_shutdown_called_through_engine(self):
        """Engine вызывает shutdown_port через adapter."""
        ports = [PortInfo(index=5, name="5", type=PortType.COPPER)]
        mac_seq = [
            [],
            [MacEntry(mac="AA:BB:CC:DD:EE:01", port_index=5)],
            [MacEntry(mac="AA:BB:CC:DD:EE:01", port_index=5)],
            [MacEntry(mac="AA:BB:CC:DD:EE:01", port_index=5)],
        ]
        adapter = _make_contract_adapter(ports=ports, counters={})
        adapter.get_mac_table.side_effect = mac_seq
        session = MagicMock()

        engine = WalkTestEngine(adapter, session)
        engine._test_port(ports[0], lambda s, m: None)

        adapter.shutdown_port.assert_called_once_with(session, ports[0])

    def test_full_run_two_ports(self):
        """Полный прогон 2 порта через contract adapter."""
        ports = [
            PortInfo(index=1, name="1", type=PortType.COPPER),
            PortInfo(index=2, name="2", type=PortType.COPPER),
        ]
        # Для каждого порта: baseline (если первый), detect, retry...
        mac_seq = [
            # Port 1
            [],  # baseline
            [MacEntry(mac="AA:BB:CC:DD:EE:01", port_index=1)],
            [MacEntry(mac="AA:BB:CC:DD:EE:01", port_index=1)],
            [MacEntry(mac="AA:BB:CC:DD:EE:01", port_index=1)],
            # Port 2
            [MacEntry(mac="AA:BB:CC:DD:EE:02", port_index=2)],
            [MacEntry(mac="AA:BB:CC:DD:EE:02", port_index=2)],
            [MacEntry(mac="AA:BB:CC:DD:EE:02", port_index=2)],
        ]
        adapter = _make_contract_adapter(ports=ports, counters={})
        adapter.get_mac_table.side_effect = mac_seq
        session = MagicMock()

        engine = WalkTestEngine(adapter, session)
        results = engine.run(ports=ports, progress_callback=lambda s, m: None)

        assert len(results) == 2
        # Оба порта shutdown
        assert adapter.shutdown_port.call_count == 2
