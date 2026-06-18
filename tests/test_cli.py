"""Tests for command-line entry points."""

from __future__ import annotations

from unittest.mock import patch

from switchlive.app.console_probe import ConsoleProbeResult
from switchlive.cli import main


def test_console_probe_cli_prints_report(capsys):
    result = ConsoleProbeResult(
        port="/dev/ttyUSB0",
        baudrate=115200,
        opened=True,
        byte_count=7,
        readable=True,
        status="readable",
        sample="switch>",
    )

    with patch("switchlive.cli.probe_console", return_value=[result]) as probe:
        code = main(["console-probe", "--port", "/dev/ttyUSB0", "--baudrates", "115200"])

    assert code == 0
    probe.assert_called_once()
    text = capsys.readouterr().out
    assert "/dev/ttyUSB0 @ 115200: READABLE" in text
