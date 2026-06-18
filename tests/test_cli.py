"""Tests for command-line entry points."""

from __future__ import annotations

import subprocess
from unittest.mock import patch

from switchlive.app.console_probe import ConsoleProbeResult
from switchlive.cli import main, run_update


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


def test_update_runs_git_pull_and_pipx_install(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / "pyproject.toml").write_text('name = "switchlive"\n', encoding="utf-8")
    calls = []

    def fake_run(command, cwd, check):
        calls.append((command, cwd, check))
        return subprocess.CompletedProcess(command, 0)

    with patch("switchlive.cli.subprocess.run", side_effect=fake_run):
        code = run_update(tmp_path)

    assert code == 0
    assert calls == [
        (["git", "pull"], tmp_path, False),
        (["pipx", "install", "--force", "."], tmp_path, False),
    ]


def test_update_returns_subprocess_failure(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / "pyproject.toml").write_text('name = "switchlive"\n', encoding="utf-8")

    with patch(
        "switchlive.cli.subprocess.run",
        return_value=subprocess.CompletedProcess(["git", "pull"], 7),
    ):
        code = run_update(tmp_path)

    assert code == 7


def test_update_requires_checkout(tmp_path):
    assert run_update(tmp_path) == 2
