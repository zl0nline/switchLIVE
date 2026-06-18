"""Tests for operator console helpers (#13)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from switchlive.config import Config
from switchlive.core.models import LinkStatus, MacEntry, PortInfo, PortType, PortVerdict
from switchlive.ui.console import (
    _active_ports_from_link_status,
    _configure_poe_test,
    _configure_walk_test,
    _DiscoveryProgressPrinter,
    _format_port_result,
    _prepare_uplink,
    _print_bottom_menu,
    _progress_bar,
    _run_discovery_wizard,
    _verdict_label,
    _wait_for_uplink,
    show_start_menu,
)


def _strip_ansi(text: str) -> str:
    import re

    return re.sub(r"\033\[[0-9;]*m", "", text)


class TestConsoleFormatting:
    def test_progress_bar(self):
        assert _progress_bar(0, 4).endswith("0/4")
        assert _progress_bar(2, 4).endswith("2/4")
        assert _progress_bar(5, 4).endswith("4/4")

    def test_verdict_label(self):
        assert "[OK]" in _verdict_label(PortVerdict.PASS)
        assert "[WARN]" in _verdict_label(PortVerdict.WARN)
        assert "[FAIL]" in _verdict_label(PortVerdict.FAIL)

    def test_format_port_result(self):
        result = MagicMock()
        result.verdict = PortVerdict.PASS
        result.port = PortInfo(index=25, name="25", type=PortType.SFP_PLUS)
        text = _strip_ansi(_format_port_result(result))
        assert "Порт 25" in text
        assert "sfp_plus" in text

    def test_bottom_menu_contains_exit_hint(self, capsys):
        _print_bottom_menu()
        text = capsys.readouterr().out
        assert "Команды:" in text
        assert "0 выход" in text

    def test_discovery_progress_compacts_port_failures(self, capsys):
        progress = _DiscoveryProgressPrinter()

        progress("Найдено COM-портов: 2")
        progress("Проверка порта /dev/ttyUSB0...")
        progress("Не удалось открыть /dev/ttyUSB0: noisy low-level error")
        progress.finish()

        text = capsys.readouterr().out
        assert "1/2" in text
        assert "/dev/ttyUSB0" in text
        assert "noisy low-level error" not in text


class TestConfigureWalkTest:
    @patch("switchlive.ui.console.run_discovery")
    def test_discovery_uses_config_login_file(self, run_discovery):
        config = Config(standard_login_file="custom-login.txt")

        _run_discovery_wizard(config)

        assert run_discovery.call_args.kwargs["standard_logins_path"] == "custom-login.txt"
        assert run_discovery.call_args.kwargs["baudrates"] == (9600, 115200)

    @patch("switchlive.ui.console.run_discovery")
    def test_discovery_uses_config_baudrates(self, run_discovery):
        config = Config.from_dict({"serial": {"default_baudrates": [115200, 9600, 57600]}})

        _run_discovery_wizard(config)

        assert run_discovery.call_args.kwargs["baudrates"] == (115200, 9600, 57600)

    @patch("switchlive.ui.console.check_iperf3_available", return_value=False)
    @patch("builtins.input", return_value="")
    def test_no_iperf_available(self, _input, _available):
        cfg = _configure_walk_test()
        assert cfg.run_traffic is False
        assert cfg.iperf_config is None
        assert cfg.run_poe is False
        assert cfg.poe_camera_ip == ""

    @patch("switchlive.ui.console.check_iperf3_available", return_value=True)
    @patch("builtins.input", return_value="192.0.2.10")
    def test_iperf_config_without_poe_prompt(self, _input, _available):
        cfg = _configure_walk_test()
        assert cfg.run_traffic is True
        assert cfg.iperf_config.server_host == "192.0.2.10"
        assert cfg.run_poe is False
        assert cfg.poe_camera_ip == ""

    @patch("switchlive.ui.console.check_iperf3_available", return_value=True)
    @patch("builtins.input", return_value="")
    def test_uses_config_defaults(self, _input, _available):
        config = Config(
            iperf_server_host="192.0.2.30",
            iperf_server_port=5202,
            iperf_duration=7,
            iperf_min_throughput_mbps=100.0,
            iperf_max_loss_percent=1.5,
            link_timeout_sec=12,
            poe_timeout_sec=34,
            max_timeout_sec=56,
        )

        cfg = _configure_walk_test(config)

        assert cfg.run_traffic is True
        assert cfg.iperf_config.server_host == "192.0.2.30"
        assert cfg.iperf_config.server_port == 5202
        assert cfg.iperf_config.duration_sec == 7
        assert cfg.iperf_config.min_throughput_mbps == 100.0
        assert cfg.iperf_config.max_loss_percent == 1.5
        assert cfg.timeout_policy.base == 12
        assert cfg.timeout_policy.poe == 34
        assert cfg.timeout_policy.max == 56
        assert cfg.run_poe is False
        assert cfg.poe_camera_ip == ""

    @patch("builtins.input", return_value="192.0.2.20")
    def test_poe_config_is_separate(self, _input):
        cfg = _configure_poe_test()

        assert cfg.run_traffic is False
        assert cfg.run_poe is True
        assert cfg.poe_camera_ip == "192.0.2.20"


class TestConsoleInterrupts:
    @patch("switchlive.ui.console._handle_test_menu", side_effect=KeyboardInterrupt)
    @patch("builtins.input", return_value="2")
    def test_ctrl_c_during_action_exits_cleanly(self, _input, _handler, capsys):
        show_start_menu()

        text = _strip_ansi(capsys.readouterr().out)
        assert "Операция прервана оператором" in text


class TestUplinkPreflight:
    def test_active_ports_from_link_status(self):
        down = PortInfo(index=9, name="9", link_status=LinkStatus.DOWN)
        up = PortInfo(index=10, name="10", link_status=LinkStatus.UP)

        assert _active_ports_from_link_status([down, up]) == [up]

    @patch("switchlive.ui.console.time.sleep", return_value=None)
    def test_wait_for_uplink_detects_link_up_after_connect(self, _sleep):
        down = PortInfo(index=9, name="9", type=PortType.COMBO, link_status=LinkStatus.DOWN)
        up = PortInfo(index=9, name="9", type=PortType.COMBO, link_status=LinkStatus.UP)
        adapter = MagicMock()
        adapter.list_ports.side_effect = [[down], [up]]
        adapter.get_mac_table.return_value = []

        result = _wait_for_uplink(
            adapter,
            MagicMock(),
            baseline={},
            uplinks=[down],
            config=Config(link_timeout_sec=1),
        )

        assert result == up

    @patch("switchlive.ui.console._wait_for_uplink", return_value=None)
    @patch("builtins.input", return_value="")
    def test_prepare_uplink_can_continue_after_manual_confirmation(self, _input, _wait):
        uplink = PortInfo(index=9, name="9", type=PortType.COMBO, link_status=LinkStatus.DOWN)
        adapter = MagicMock()
        adapter.get_mac_table.return_value = []

        ready, detected = _prepare_uplink(adapter, MagicMock(), [uplink], Config())

        assert ready is True
        assert detected is None

    def test_prepare_uplink_detects_existing_macs_on_plain_copper(self, capsys):
        ports = [
            PortInfo(index=1, name="1", type=PortType.COPPER),
            PortInfo(index=9, name="9", type=PortType.COPPER),
        ]
        adapter = MagicMock()
        adapter.get_mac_table.return_value = [
            MacEntry(mac="AA:BB:CC:DD:EE:01", port_index=9),
            MacEntry(mac="AA:BB:CC:DD:EE:02", port_index=9),
            MacEntry(mac="AA:BB:CC:DD:EE:03", port_index=9),
        ]

        ready, detected = _prepare_uplink(adapter, MagicMock(), ports, Config())

        assert ready is True
        assert detected is not None
        assert detected.index == 9
        assert "Аплинк готов: порт 9" in _strip_ansi(capsys.readouterr().out)
