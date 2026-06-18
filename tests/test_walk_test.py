"""Тесты walk-test engine (#8)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from switchlive.app.walk_test import (
    WalkTestConfig,
    WalkTestEngine,
    WalkTestState,
)
from switchlive.core.models import PortInfo, PortType, PortVerdict


def _make_mock_adapter(ports=None, mac_table=None, counters=None,
                         mac_table_sequence=None):
    """Создать полностью настроенный mock adapter.

    mac_table_sequence: список возвращаемых значений для последовательных
    вызовов get_mac_table (baseline → current → current ...).
    """
    adapter = MagicMock()
    adapter.list_ports.return_value = ports or []
    if mac_table_sequence is not None:
        adapter.get_mac_table.side_effect = mac_table_sequence
    else:
        adapter.get_mac_table.return_value = mac_table or []
    adapter.get_counters.return_value = counters or {}
    adapter.shutdown_port.return_value = None
    return adapter


class TestWalkTestConfig:
    def test_defaults(self):
        cfg = WalkTestConfig()
        assert cfg.skip_management is True
        assert cfg.skip_console is True
        assert cfg.run_poe is True

    def test_custom(self):
        cfg = WalkTestConfig(skip_management=False, run_poe=False)
        assert cfg.skip_management is False
        assert cfg.run_poe is False


class TestWalkTestEngine:
    def test_skip_management_ports(self):
        mgmt = PortInfo(index=0, name="mgmt", type=PortType.MANAGEMENT)
        copper = PortInfo(index=1, name="1", type=PortType.COPPER)
        adapter = _make_mock_adapter(ports=[mgmt, copper])
        session = MagicMock()

        engine = WalkTestEngine(adapter, session)
        filtered = engine._filter_ports([mgmt, copper])

        assert mgmt not in filtered
        assert copper in filtered

    def test_skip_console_ports(self):
        console = PortInfo(index=99, name="console", type=PortType.CONSOLE)
        copper = PortInfo(index=1, name="1", type=PortType.COPPER)
        adapter = _make_mock_adapter(ports=[console, copper])
        session = MagicMock()

        engine = WalkTestEngine(adapter, session)
        filtered = engine._filter_ports([console, copper])

        assert console not in filtered
        assert copper in filtered

    def test_filter_keeps_sfp_and_combo(self):
        sfp = PortInfo(index=25, name="25", type=PortType.SFP)
        combo = PortInfo(index=27, name="27", type=PortType.COMBO)
        adapter = _make_mock_adapter()
        session = MagicMock()

        engine = WalkTestEngine(adapter, session)
        filtered = engine._filter_ports([sfp, combo])

        assert sfp in filtered
        assert combo in filtered

    def test_shutdown_called_for_port(self):
        port = PortInfo(index=5, name="5", type=PortType.COPPER)
        adapter = _make_mock_adapter(ports=[port])
        session = MagicMock()

        engine = WalkTestEngine(adapter, session)
        engine._shutdown_port(port, lambda s, m: None)

        adapter.shutdown_port.assert_called_once()

    def test_shutdown_added_to_set(self):
        port = PortInfo(index=5, name="5", type=PortType.COPPER)
        adapter = _make_mock_adapter()
        session = MagicMock()

        engine = WalkTestEngine(adapter, session)
        engine._shutdown_port(port, lambda s, m: None)

        assert 5 in engine.shutdown_ports

    def test_counters_clean_pass(self):
        """Чистые counters → PASS."""
        from switchlive.core.models import MacEntry

        port = PortInfo(index=1, name="1", type=PortType.COPPER)
        # baseline: пусто, затем MAC появляется
        mac_seq = [
            [],  # baseline
            [MacEntry(mac="AA:BB:CC:DD:EE:01", port_index=1)],  # after connect
            [MacEntry(mac="AA:BB:CC:DD:EE:01", port_index=1)],  # retries
            [MacEntry(mac="AA:BB:CC:DD:EE:01", port_index=1)],
        ]
        adapter = _make_mock_adapter(
            ports=[port],
            mac_table_sequence=mac_seq,
            counters={"crc": 0, "drops": 0},
        )
        session = MagicMock()

        engine = WalkTestEngine(adapter, session)
        result = engine._test_port(port, lambda s, m: None)

        assert result.verdict == PortVerdict.PASS

    def test_counters_with_errors_warn(self):
        """CRC/drops > 0 → WARN."""
        from switchlive.core.models import MacEntry

        port = PortInfo(index=1, name="1", type=PortType.COPPER)
        mac_seq = [
            [],
            [MacEntry(mac="AA:BB:CC:DD:EE:01", port_index=1)],
            [MacEntry(mac="AA:BB:CC:DD:EE:01", port_index=1)],
            [MacEntry(mac="AA:BB:CC:DD:EE:01", port_index=1)],
        ]
        adapter = _make_mock_adapter(
            ports=[port],
            mac_table_sequence=mac_seq,
            counters={"crc": 5, "drops": 2},
        )
        session = MagicMock()

        engine = WalkTestEngine(adapter, session)
        result = engine._test_port(port, lambda s, m: None)

        assert result.verdict == PortVerdict.WARN
        assert any("CRC" in n for n in result.notes)

    def test_port_not_detected_warn_without_shutdown(self):
        """Порт не найден → WARN, порт остаётся включённым."""
        port = PortInfo(index=1, name="1", type=PortType.COPPER)
        adapter = _make_mock_adapter(ports=[port], mac_table=[])
        session = MagicMock()

        engine = WalkTestEngine(adapter, session)
        result = engine._test_port(port, lambda s, m: None)

        assert result.verdict == PortVerdict.WARN
        assert result.port is port
        assert not adapter.shutdown_port.called

    def test_full_walk_test_run(self):
        """Полный прогон по 2 портам."""
        from switchlive.core.models import MacEntry

        ports = [
            PortInfo(index=1, name="1", type=PortType.COPPER),
            PortInfo(index=2, name="2", type=PortType.COPPER),
        ]
        adapter = _make_mock_adapter(
            ports=ports,
            mac_table=[MacEntry(mac="AA:BB:CC:DD:EE:01", port_index=1)],
            counters={"crc": 0, "drops": 0},
        )
        session = MagicMock()

        engine = WalkTestEngine(adapter, session)
        results = engine.run(ports=ports, progress_callback=lambda s, m: None)

        assert len(results) == 2
        assert engine.state == WalkTestState.DONE

    def test_run_can_stop_before_next_port(self):
        """Оператор может закончить тест и получить частичные результаты."""
        from switchlive.core.models import MacEntry

        ports = [
            PortInfo(index=1, name="1", type=PortType.COPPER),
            PortInfo(index=2, name="2", type=PortType.COPPER),
        ]
        adapter = _make_mock_adapter(
            ports=ports,
            mac_table=[MacEntry(mac="AA:BB:CC:DD:EE:01", port_index=1)],
            counters={"crc": 0, "drops": 0},
        )
        decisions = iter([True, False])

        engine = WalkTestEngine(adapter, MagicMock())
        results = engine.run(
            ports=ports,
            progress_callback=lambda s, m: None,
            continue_callback=lambda port, number, total: next(decisions),
        )

        assert len(results) == 1
        assert engine.results == results

    def test_poe_test_called_for_poe_port(self):
        """PoE тест вызывается для PoE-порта."""
        from switchlive.core.models import MacEntry

        port = PortInfo(
            index=1, name="1", type=PortType.COPPER, supports_poe=True
        )
        mac_seq = [
            [],
            [MacEntry(mac="AA:BB:CC:DD:EE:01", port_index=1)],
            [MacEntry(mac="AA:BB:CC:DD:EE:01", port_index=1)],
            [MacEntry(mac="AA:BB:CC:DD:EE:01", port_index=1)],
        ]
        adapter = _make_mock_adapter(
            ports=[port],
            mac_table_sequence=mac_seq,
            counters={},
        )
        adapter.get_poe_status.return_value = {"status": "ON", "power_w": "15.4"}
        session = MagicMock()

        engine = WalkTestEngine(adapter, session)
        result = engine._test_port(port, lambda s, m: None)

        adapter.get_poe_status.assert_called_once()
        assert any("PoE" in n for n in result.notes)

    def test_sfp_test_called_for_sfp_port(self):
        """SFP тест вызывается для SFP-порта."""
        from switchlive.core.models import MacEntry

        port = PortInfo(index=9, name="9", type=PortType.SFP_PLUS)
        mac_seq = [
            [],
            [MacEntry(mac="AA:BB:CC:DD:EE:01", port_index=9)],
            [MacEntry(mac="AA:BB:CC:DD:EE:01", port_index=9)],
            [MacEntry(mac="AA:BB:CC:DD:EE:01", port_index=9)],
        ]
        adapter = _make_mock_adapter(
            ports=[port],
            mac_table_sequence=mac_seq,
            counters={},
        )
        adapter.get_transceiver.return_value = {"vendor": "Finisar"}
        session = MagicMock()

        engine = WalkTestEngine(adapter, session)
        result = engine._test_port(port, lambda s, m: None)

        adapter.get_transceiver.assert_called_once()
        assert any("SFP" in n for n in result.notes)

    def test_failed_traffic_does_not_shutdown_port(self):
        """Если iperf FAIL, порт оставляем включённым для повторного теста."""
        from switchlive.app.traffic_iperf import IperfConfig, IperfResult
        from switchlive.core.models import MacEntry

        port = PortInfo(index=1, name="1", type=PortType.COPPER)
        mac_seq = [
            [],
            [MacEntry(mac="AA:BB:CC:DD:EE:01", port_index=1)],
        ]
        adapter = _make_mock_adapter(
            ports=[port],
            mac_table_sequence=mac_seq,
            counters={},
        )
        session = MagicMock()
        config = WalkTestConfig(
            run_traffic=True,
            iperf_config=IperfConfig(server_host="192.0.2.10"),
            detection_retries=1,
            detection_delay=0,
        )

        with patch(
            "switchlive.app.traffic_iperf.run_iperf_test",
            return_value=IperfResult(verdict="FAIL", error="no route"),
        ):
            result = WalkTestEngine(adapter, session, config)._test_port(port, lambda s, m: None)

        assert result.traffic_passed is False
        assert not adapter.shutdown_port.called
        adapter.no_shutdown_port.assert_called_once()

    def test_passed_traffic_shutdowns_port(self):
        """Если iperf PASS, порт выключаем как успешно проверенный."""
        from switchlive.app.traffic_iperf import IperfConfig, IperfResult
        from switchlive.core.models import MacEntry

        port = PortInfo(index=1, name="1", type=PortType.COPPER)
        mac_seq = [
            [],
            [MacEntry(mac="AA:BB:CC:DD:EE:01", port_index=1)],
        ]
        adapter = _make_mock_adapter(
            ports=[port],
            mac_table_sequence=mac_seq,
            counters={},
        )
        session = MagicMock()
        config = WalkTestConfig(
            run_traffic=True,
            iperf_config=IperfConfig(server_host="192.0.2.10"),
            detection_retries=1,
            detection_delay=0,
        )

        with patch(
            "switchlive.app.traffic_iperf.run_iperf_test",
            return_value=IperfResult(success=True, throughput_mbps=100.0, verdict="PASS"),
        ):
            result = WalkTestEngine(adapter, session, config)._test_port(port, lambda s, m: None)

        assert result.traffic_passed is True
        adapter.shutdown_port.assert_called_once()

    def test_gigabit_port_with_94m_iperf_gets_bottleneck_hint(self):
        """1G link with ~100M iperf means bottleneck is probably elsewhere."""
        from switchlive.app.traffic_iperf import IperfConfig, IperfResult
        from switchlive.core.models import MacEntry

        port = PortInfo(index=27, name="27", type=PortType.COMBO, actual_speed=1000)
        mac_seq = [
            [],
            [MacEntry(mac="AA:BB:CC:DD:EE:01", port_index=27)],
        ]
        adapter = _make_mock_adapter(
            ports=[port],
            mac_table_sequence=mac_seq,
            counters={},
        )
        session = MagicMock()
        config = WalkTestConfig(
            run_traffic=True,
            iperf_config=IperfConfig(server_host="192.0.2.10"),
            detection_retries=1,
            detection_delay=0,
            run_sfp=False,
        )

        with patch(
            "switchlive.app.traffic_iperf.run_iperf_test",
            return_value=IperfResult(success=True, throughput_mbps=94.0, verdict="PASS"),
        ):
            result = WalkTestEngine(adapter, session, config)._test_port(port, lambda s, m: None)

        assert result.verdict == PortVerdict.WARN
        assert any("bottleneck" in note for note in result.notes)
