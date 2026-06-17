"""Тесты port detection (#9)."""

from __future__ import annotations

from unittest.mock import MagicMock

from switchlive.app.port_detection import (
    detect_active_port,
    detect_active_port_with_retry,
    detect_existing_uplink_by_mac_count,
    take_mac_baseline,
)
from switchlive.core.models import LinkStatus, MacEntry, PortInfo


def _make_adapter(mac_entries: list = None) -> MagicMock:
    """Создать mock adapter с заданным MAC-выводом."""
    adapter = MagicMock()
    adapter.get_mac_table.return_value = mac_entries or []
    return adapter


def _make_session() -> MagicMock:
    return MagicMock()


class TestBaseline:
    def test_empty(self):
        adapter = _make_adapter([])
        baseline = take_mac_baseline(adapter, _make_session())
        assert baseline == {}

    def test_with_entries(self):
        entries = [
            MacEntry(mac="AA:BB:CC:DD:EE:01", port_index=1),
            MacEntry(mac="AA:BB:CC:DD:EE:02", port_index=2),
        ]
        adapter = _make_adapter(entries)
        baseline = take_mac_baseline(adapter, _make_session())
        assert len(baseline) == 2
        assert "AA:BB:CC:DD:EE:01" in baseline

    def test_baseline_excludes_new(self):
        """Baseline — это снимок ДО подключения."""
        entries = [MacEntry(mac="AA:BB:CC:DD:EE:01", port_index=1)]
        adapter = _make_adapter(entries)
        baseline = take_mac_baseline(adapter, _make_session())
        assert "AA:BB:CC:DD:EE:01" in baseline
        assert "AA:BB:CC:DD:EE:99" not in baseline


class TestDetectActivePort:
    def _setup(self, baseline_macs, current_macs, ports):
        adapter = MagicMock()
        adapter.get_mac_table.return_value = current_macs
        baseline = {mac: MacEntry(mac=mac, port_index=0) for mac in baseline_macs}
        return adapter, baseline

    def test_single_new_mac(self):
        """Один новый MAC → порт найден."""
        baseline = {"AA:BB:CC:DD:EE:01"}
        current = [
            MacEntry(mac="AA:BB:CC:DD:EE:01", port_index=1),  # old
            MacEntry(mac="AA:BB:CC:DD:EE:99", port_index=3),  # new!
        ]
        ports = [PortInfo(index=i, name=str(i)) for i in range(1, 6)]

        adapter = MagicMock()
        adapter.get_mac_table.return_value = current
        baseline_dict = {mac: MacEntry(mac=mac, port_index=0) for mac in baseline}

        result = detect_active_port(adapter, _make_session(), baseline_dict, ports)

        assert result.port is not None
        assert result.port.index == 3
        assert result.method == "mac_delta"
        assert result.confidence == "high"

    def test_no_new_macs(self):
        """Нет новых MAC — порт не найден."""
        baseline = {"AA:BB:CC:DD:EE:01"}
        current = [MacEntry(mac="AA:BB:CC:DD:EE:01", port_index=1)]
        ports = [PortInfo(index=i, name=str(i)) for i in range(1, 6)]

        adapter = MagicMock()
        adapter.get_mac_table.return_value = current
        baseline_dict = {mac: MacEntry(mac=mac, port_index=0) for mac in baseline}

        result = detect_active_port(adapter, _make_session(), baseline_dict, ports)

        assert result.port is None
        assert result.confidence == "low"
        assert len(result.warnings) > 0

    def test_no_new_macs_detects_single_live_link(self):
        """Если MAC не появился, но ожидаемый порт link up — порт найден."""
        port = PortInfo(index=10, name="10")
        live = PortInfo(index=10, name="10", link_status=LinkStatus.UP, actual_speed=100, duplex="Full")
        adapter = MagicMock()
        adapter.get_mac_table.return_value = []
        adapter.list_ports.return_value = [live]

        result = detect_active_port(adapter, _make_session(), {}, [port])

        assert result.port is live
        assert result.method == "link_status"
        assert result.confidence == "medium"

    def test_multiple_active_ports(self):
        """Несколько портов с новыми MAC — неоднозначно."""
        current = [
            MacEntry(mac="AA:BB:CC:DD:EE:0A", port_index=2),
            MacEntry(mac="AA:BB:CC:DD:EE:0B", port_index=4),
        ]
        ports = [PortInfo(index=i, name=str(i)) for i in range(1, 6)]

        adapter = MagicMock()
        adapter.get_mac_table.return_value = current

        result = detect_active_port(adapter, _make_session(), {}, ports)

        assert result.port is None
        assert result.confidence == "low"
        assert any("Несколько" in w for w in result.warnings)

    def test_shutdown_ports_ignored(self):
        """Shutdown порты не учитываются."""
        current = [
            MacEntry(mac="AA:BB:CC:DD:EE:0A", port_index=1),  # shutdown
            MacEntry(mac="AA:BB:CC:DD:EE:0B", port_index=3),  # active
        ]
        ports = [PortInfo(index=i, name=str(i)) for i in range(1, 6)]

        adapter = MagicMock()
        adapter.get_mac_table.return_value = current

        result = detect_active_port(
            adapter, _make_session(), {}, ports, shutdown_ports={1, 2}
        )

        assert result.port is not None
        assert result.port.index == 3

    def test_unknown_port_index(self):
        """MAC на неизвестном порту — warning."""
        current = [MacEntry(mac="AA:BB:CC:DD:EE:0A", port_index=99)]
        ports = [PortInfo(index=i, name=str(i)) for i in range(1, 6)]

        adapter = MagicMock()
        adapter.get_mac_table.return_value = current

        result = detect_active_port(adapter, _make_session(), {}, ports)

        assert result.port is None
        assert len(result.warnings) > 0


class TestDetectExistingUplink:
    def test_detects_port_with_most_existing_macs(self):
        current = [
            MacEntry(mac="AA:BB:CC:DD:EE:01", port_index=9),
            MacEntry(mac="AA:BB:CC:DD:EE:02", port_index=9),
            MacEntry(mac="AA:BB:CC:DD:EE:03", port_index=9),
            MacEntry(mac="AA:BB:CC:DD:EE:04", port_index=10),
        ]
        ports = [PortInfo(index=9, name="9"), PortInfo(index=10, name="10")]
        adapter = MagicMock()
        adapter.get_mac_table.return_value = current

        result = detect_existing_uplink_by_mac_count(adapter, _make_session(), ports)

        assert result.port is not None
        assert result.port.index == 9
        assert result.method == "existing_mac_count"
        assert result.confidence == "high"

    def test_no_existing_macs(self):
        adapter = MagicMock()
        adapter.get_mac_table.return_value = []

        result = detect_existing_uplink_by_mac_count(
            adapter, _make_session(), [PortInfo(index=9, name="9")]
        )

        assert result.port is None


class TestDetectWithRetry:
    def test_found_on_first_try(self):
        current = [MacEntry(mac="AA:BB:CC:DD:EE:0A", port_index=1)]
        ports = [PortInfo(index=1, name="1")]
        adapter = MagicMock()
        adapter.get_mac_table.return_value = current

        result = detect_active_port_with_retry(
            adapter, _make_session(), {}, ports, max_retries=3, retry_delay=0.01
        )
        assert result.port is not None

    def test_found_on_retry(self):
        """MAC появляется не сразу — на третьей попытке."""
        ports = [PortInfo(index=2, name="2")]
        adapter = MagicMock()
        # Первые два вызова — пусто, третий — MAC
        adapter.get_mac_table.side_effect = [
            [],
            [],
            [MacEntry(mac="AA:BB:CC:DD:EE:0A", port_index=2)],
        ]

        result = detect_active_port_with_retry(
            adapter, _make_session(), {}, ports, max_retries=3, retry_delay=0.01
        )
        assert result.port is not None
        assert result.port.index == 2

    def test_never_found(self):
        ports = [PortInfo(index=1, name="1")]
        adapter = MagicMock()
        adapter.get_mac_table.return_value = []

        result = detect_active_port_with_retry(
            adapter, _make_session(), {}, ports, max_retries=2, retry_delay=0.01
        )
        assert result.port is None
