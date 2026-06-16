"""Тесты iperf traffic probe (#10)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from switchlive.tests.traffic_iperf import (
    IperfConfig,
    IperfResult,
    _evaluate_verdict,
    _parse_iperf_json,
    _parse_iperf_text,
    check_iperf3_available,
    check_server_reachable,
    run_iperf_test,
)


class TestIperfConfig:
    def test_defaults(self):
        cfg = IperfConfig()
        assert cfg.server_port == 5201
        assert cfg.duration_sec == 10
        assert cfg.min_throughput_mbps == 50.0

    def test_custom(self):
        cfg = IperfConfig(server_host="192.168.1.100", duration_sec=5)
        assert cfg.server_host == "192.168.1.100"
        assert cfg.duration_sec == 5


class TestVerdictEvaluation:
    def test_pass(self):
        result = IperfResult(throughput_mbps=900, loss_percent=0)
        cfg = IperfConfig()
        assert _evaluate_verdict(result, cfg) == "PASS"

    def test_warn_low_throughput(self):
        result = IperfResult(throughput_mbps=30, loss_percent=0)
        cfg = IperfConfig()
        assert _evaluate_verdict(result, cfg) == "WARN"

    def test_warn_high_loss(self):
        result = IperfResult(throughput_mbps=900, loss_percent=10)
        cfg = IperfConfig()
        assert _evaluate_verdict(result, cfg) == "WARN"

    def test_fail_no_throughput(self):
        result = IperfResult(throughput_mbps=0)
        cfg = IperfConfig()
        assert _evaluate_verdict(result, cfg) == "FAIL"


class TestParseJson:
    def test_tcp_json(self):
        """Парсинг TCP JSON вывода iperf3."""
        data = {
            "end": {
                "sum_received": {
                    "bits_per_second": 950_000_000  # 950 Mbps
                }
            }
        }
        cfg = IperfConfig()
        result = _parse_iperf_json(json.dumps(data), cfg)
        assert result.success is True
        assert result.throughput_mbps == 950.0

    def test_udp_json(self):
        """Парсинг UDP JSON с потерями."""
        data = {
            "end": {
                "sum": {
                    "bits_per_second": 800_000_000,
                    "lost_packets": 5,
                    "total_packets": 100,
                    "jitter_ms": 0.123
                }
            }
        }
        cfg = IperfConfig()
        result = _parse_iperf_json(json.dumps(data), cfg)
        assert result.throughput_mbps == 800.0
        assert result.lost_packets == 5
        assert result.total_packets == 100
        assert result.loss_percent == 5.0

    def test_invalid_json_falls_back(self):
        """Невалидный JSON → text parser."""
        cfg = IperfConfig()
        result = _parse_iperf_json("not json at all", cfg)
        # text parser попытается найти числа
        assert isinstance(result, IperfResult)


class TestParseText:
    def test_tcp_text(self):
        """Текстовый вывод TCP."""
        output = """
[  5]   0.00-10.00  sec  1.05 GBytes   950 Mbits/sec
        """
        cfg = IperfConfig()
        result = _parse_iperf_text(output, cfg)
        assert result.throughput_mbps == 950.0

    def test_gbits_text(self):
        """Gbits/sec."""
        output = "[  5]   0.00-10.00  sec  2.1 GBytes  1800 Mbits/sec"
        cfg = IperfConfig()
        result = _parse_iperf_text(output, cfg)
        assert result.throughput_mbps == 1800.0

    def test_udp_loss_text(self):
        """Текстовый UDP с потерями."""
        output = """
[  5]   0.00-10.00  sec  100 datagrams received
        Sent:    105
        Received: 100
        Lost:    5 (4.8%)
        """
        cfg = IperfConfig()
        result = _parse_iperf_text(output, cfg)
        assert isinstance(result, IperfResult)


class TestRunIperf:
    def test_no_server_host(self):
        """Нет IP сервера → SKIP."""
        cfg = IperfConfig(server_host="")
        result = run_iperf_test(cfg)
        assert result.verdict == "SKIP"
        assert "не задан" in result.error

    @patch("switchlive.tests.traffic_iperf.check_iperf3_available", return_value=False)
    def test_iperf3_not_installed(self, _):
        cfg = IperfConfig(server_host="192.168.1.100")
        with pytest.raises(Exception, match="не установлен"):
            run_iperf_test(cfg)

    @patch("switchlive.tests.traffic_iperf.check_iperf3_available", return_value=True)
    @patch("switchlive.tests.traffic_iperf.subprocess.run")
    def test_successful_run(self, mock_run, _):
        """Успешный запуск iperf3."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({
                "end": {
                    "sum_received": {"bits_per_second": 950_000_000}
                }
            }),
            stderr="",
        )

        cfg = IperfConfig(server_host="192.168.1.100")
        result = run_iperf_test(cfg)
        assert result.success is True
        assert result.throughput_mbps == 950.0
        assert result.verdict == "PASS"

    @patch("switchlive.tests.traffic_iperf.check_iperf3_available", return_value=True)
    @patch("switchlive.tests.traffic_iperf.subprocess.run")
    def test_iperf_error(self, mock_run, _):
        """iperf3 вернул ошибку."""
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="unable to connect",
        )

        cfg = IperfConfig(server_host="192.168.1.100")
        result = run_iperf_test(cfg)
        assert result.success is False
        assert result.verdict == "FAIL"
        assert "unable to connect" in result.error

    @patch("switchlive.tests.traffic_iperf.check_iperf3_available", return_value=True)
    @patch("switchlive.tests.traffic_iperf.subprocess.run")
    def test_timeout(self, mock_run, _):
        """Таймаут iperf3."""
        import subprocess as sp

        mock_run.side_effect = sp.TimeoutExpired(cmd="iperf3", timeout=30)

        cfg = IperfConfig(server_host="192.168.1.100", timeout=30)
        result = run_iperf_test(cfg)
        assert result.success is False
        assert result.verdict == "FAIL"
        assert "timeout" in result.error.lower()


class TestCheckServer:
    @patch("socket.create_connection")
    def test_reachable(self, mock_conn):
        mock_conn.return_value.__enter__ = MagicMock()
        mock_conn.return_value.__exit__ = MagicMock(return_value=False)
        assert check_server_reachable("192.168.1.100") is True

    @patch("socket.create_connection", side_effect=OSError("refused"))
    def test_not_reachable(self, _):
        assert check_server_reachable("192.168.1.100") is False


class TestAvailability:
    def test_check_iperf3_available(self):
        """Просто проверяем, что функция не падает."""
        result = check_iperf3_available()
        assert isinstance(result, bool)
