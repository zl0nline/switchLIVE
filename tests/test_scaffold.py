"""Базовые тесты scaffold — проверка импортов и CLI."""

import importlib


def test_import_cli():
    """CLI модуль импортируется."""
    mod = importlib.import_module("switchlive.cli")
    assert hasattr(mod, "main")


def test_import_config():
    mod = importlib.import_module("switchlive.config")
    assert hasattr(mod, "Config")


def test_import_models():
    mod = importlib.import_module("switchlive.core.models")
    assert hasattr(mod, "DeviceIdentity")
    assert hasattr(mod, "PortInfo")
    assert hasattr(mod, "TestResult")


def test_import_errors():
    mod = importlib.import_module("switchlive.core.errors")
    assert hasattr(mod, "SwitchLiveError")


def test_import_credentials():
    mod = importlib.import_module("switchlive.core.credentials")
    assert hasattr(mod, "Credentials")
    assert hasattr(mod, "load_standard_logins")


def test_import_timeouts():
    mod = importlib.import_module("switchlive.core.timeouts")
    assert hasattr(mod, "TimeoutPolicy")


def test_import_diagnostics():
    mod = importlib.import_module("switchlive.diagnostics")
    assert hasattr(mod, "configure_logging")
    assert hasattr(mod, "collect_debug_bundle")


def test_import_transport_base():
    mod = importlib.import_module("switchlive.transports.base")
    assert hasattr(mod, "CommandTransport")


def test_import_serial_transport():
    mod = importlib.import_module("switchlive.transports.serial")
    assert hasattr(mod, "SerialTransport")


def test_import_session():
    mod = importlib.import_module("switchlive.sessions.cli_session")
    assert hasattr(mod, "CLISession")


def test_import_prompts():
    mod = importlib.import_module("switchlive.sessions.prompts")
    assert hasattr(mod, "find_command_prompt")
    assert hasattr(mod, "match_login_prompt")


def test_import_device_registry():
    mod = importlib.import_module("switchlive.devices.registry")
    assert hasattr(mod, "register_adapter")
    assert hasattr(mod, "find_adapter")


def test_config_defaults():
    from switchlive.config import Config
    cfg = Config()
    assert cfg.iperf_server_port == 5201
    assert cfg.iperf_parallel_streams == 4
    assert cfg.iperf_min_throughput_mbps == 50.0
    assert cfg.max_timeout_sec == 600
    assert cfg.debug is False
