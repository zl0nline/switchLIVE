"""Tests for debug logging and diagnostic bundles."""

from __future__ import annotations

import json
import logging
from zipfile import ZipFile

from switchlive.config import Config
from switchlive.diagnostics import (
    collect_debug_bundle,
    configure_logging,
    redact_text,
    sanitize_data,
)


def test_redact_text_masks_common_secrets():
    text = "password: hunter2\nenable_password=supersecret\ntoken = abc123"

    redacted = redact_text(text)

    assert "hunter2" not in redacted
    assert "supersecret" not in redacted
    assert "abc123" not in redacted
    assert "password: ***" in redacted


def test_sanitize_data_masks_secret_keys():
    data = {
        "username": "admin",
        "password": "admin",
        "nested": {"api_key": "123"},
    }

    assert sanitize_data(data) == {
        "username": "admin",
        "password": "***",
        "nested": {"api_key": "***"},
    }


def test_config_loads_nested_example_shape(tmp_path):
    config_path = tmp_path / "switchlive.json"
    config_path.write_text(
        json.dumps(
            {
                "iperf": {"server_host": "192.0.2.10", "server_port": 5202},
                "reports": {"report_dir": "out", "db_path": "history.sqlite"},
                "timeouts": {"link_sec": 11, "poe_sec": 22},
                "debug": True,
            }
        ),
        encoding="utf-8",
    )

    config = Config.load(config_path)

    assert config.iperf_server_host == "192.0.2.10"
    assert config.iperf_server_port == 5202
    assert config.report_dir == "out"
    assert config.db_path == "history.sqlite"
    assert config.link_timeout_sec == 11
    assert config.poe_timeout_sec == 22
    assert config.debug is True


def test_configure_logging_writes_redacted_debug_log(tmp_path):
    context = configure_logging(debug=True, log_dir=tmp_path / "logs")
    logger = logging.getLogger("switchlive.tests")

    logger.debug("password: hunter2")
    logging.shutdown()

    assert context.log_file is not None
    text = context.log_file.read_text(encoding="utf-8")
    assert "hunter2" not in text
    assert "password: ***" in text


def test_collect_debug_bundle_sanitizes_config_log_and_reports(tmp_path):
    config_path = tmp_path / "switchlive.json"
    report_dir = tmp_path / "reports"
    report_dir.mkdir()
    (report_dir / "report.html").write_text("password: reportsecret", encoding="utf-8")
    config_path.write_text(
        json.dumps(
            {
                "reports": {"report_dir": str(report_dir), "db_path": str(tmp_path / "history.sqlite")},
                "password": "configsecret",
            }
        ),
        encoding="utf-8",
    )
    config = Config.load(config_path)
    context = configure_logging(debug=True, log_dir=tmp_path / "logs")
    logging.getLogger("switchlive.tests").debug("token: logsecret")
    logging.shutdown()

    bundle = collect_debug_bundle(
        config=config,
        config_path=config_path,
        context=context,
        output_dir=tmp_path / "bundles",
    )

    with ZipFile(bundle) as archive:
        names = set(archive.namelist())
        assert "environment.txt" in names
        assert "config.sanitized.json" in names
        assert any(name.startswith("logs/") for name in names)
        assert "reports/report.html" in names
        combined = "\n".join(
            archive.read(name).decode("utf-8")
            for name in names
            if name.endswith((".json", ".log", ".html", ".txt"))
        )

    assert "configsecret" not in combined
    assert "logsecret" not in combined
    assert "reportsecret" not in combined
