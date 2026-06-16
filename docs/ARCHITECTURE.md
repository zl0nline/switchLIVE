# switchLIVE Architecture

switchLIVE starts as a switch testing utility, but the core must support other
console-controlled devices later: routers, OLTs, UPS/PDU, media converters,
radios, and any equipment managed through an interactive CLI.

The main rule: device-specific behavior lives in adapters and profiles. The
core only knows how to connect, run commands, execute test plans, collect
results, and report them.

## Goals

- Keep serial/SSH/Telnet access separate from device logic.
- Keep prompt/login/paging handling separate from test logic.
- Make D-Link switch support the first adapter, not the architecture center.
- Make test plans reusable for future device classes.
- Keep the MVP small: Python 3, minimal dependencies, clear module boundaries.

## Layers

### CLI and UI

Operator-facing console workflow.

Responsibilities:
- start menu;
- "Определение коммутатора";
- manual credential prompts;
- test profile selection;
- progress bars, statuses, warnings, final summary;
- debug/log visibility.

This layer must not parse vendor CLI output directly. It calls application
services and renders state.

### Application Services

Use-case orchestration.

Responsibilities:
- device discovery flow;
- test session setup;
- walk-test orchestration;
- finalization flow;
- report/history coordination.

This layer wires transports, sessions, device adapters, tests, storage, and UI.

### Transport

Raw connection to a device.

Initial transport:
- serial/COM via USB-UART or RJ45-serial cable.

Future transports:
- SSH;
- Telnet.

Transport responsibilities:
- open/close connection;
- read/write bytes or text;
- expose timeouts;
- surface transport errors;
- stay unaware of vendors, prompts, commands, or tests.

### Session

Interactive CLI session on top of a transport.

Responsibilities:
- wake prompt;
- detect login/password prompts;
- try credentials from `standart_login.txt`;
- request manual credentials when needed;
- detect command prompt;
- run commands and collect output;
- handle CLI pagers;
- mask secrets in logs.

Session may use vendor/profile hints for prompt patterns and pager commands,
but it must remain reusable across device types.

### Device Discovery

Find and identify a connected device.

Responsibilities:
- scan available transports, starting with COM ports;
- try safe identification commands;
- infer vendor, model, firmware, serial number when possible;
- choose a matching `DeviceProfile`;
- return an `UnknownDevice` when unsupported instead of crashing.

Discovery is plugin-like: each vendor/device family may provide detectors.

### Device Profiles and Adapters

Vendor/model-specific behavior.

Profiles describe static capabilities:
- vendor;
- model/family;
- prompt patterns;
- default serial settings;
- port naming scheme;
- supported features: PoE, SFP, counters, DOM, reset;
- command names or command templates.

Adapters implement behavior:
- parse `show version`;
- parse ports/status;
- parse MAC table;
- parse counters;
- read PoE state;
- read SFP DOM;
- shutdown/no shutdown ports;
- factory reset/reload.

D-Link models from `SUPPORTED.md` should be grouped into families when commands
and parsers are compatible.

### Normalized Device Model

Shared domain objects used by tests and reports.

Core objects should include:
- `DeviceIdentity`;
- `DeviceProfile`;
- `PortInfo`;
- `PortStatus`;
- `CommandResult`;
- `TestPlan`;
- `TestStep`;
- `TestResult`;
- `Report`.

Tests and reports must use normalized objects, not raw CLI strings.

### Test Engine

Reusable state machines and test steps.

Initial switch walk-test:
1. Wait for cable/link.
2. Detect active port.
3. Test link speed, duplex, counters.
4. Run traffic test.
5. Optionally run PoE test.
6. Optionally run SFP/SFP+ test.
7. Store per-port result.
8. Shutdown tested port.
9. Ask operator to move cable.

The engine owns state transitions, timeouts, cancellation, retries, and result
aggregation. Device adapters provide commands and parsers.

### Probes

External or local test helpers.

Initial probes:
- `iperf3` client launched through `subprocess`;
- PoE camera reachability check.

Probe code must be separate from device adapters. A future test may use a
different traffic generator without changing D-Link support.

### Storage

Local persistent history.

Initial storage:
- SQLite through Python standard library.

Responsibilities:
- save device identity;
- save test runs;
- save per-port results;
- save comments/operator;
- support lookup by serial number.

Storage schema must not be D-Link-specific.

### Reports

Human and machine-readable outputs.

Initial formats:
- HTML;
- CSV.

Possible later format:
- PDF.

Reports consume normalized `Report` data and should not call device adapters.

## Proposed Package Structure

```text
switchlive/
  cli.py
  config.py
  app/
    discovery.py
    test_runner.py
    finalization.py
  core/
    models.py
    errors.py
    timeouts.py
    credentials.py
  transports/
    base.py
    serial.py
  sessions/
    cli_session.py
    prompts.py
    pager.py
  devices/
    base.py
    registry.py
    dlink/
      profiles.py
      detector.py
      adapter.py
      parsers.py
  tests/
    plans.py
    walk_test.py
    port_detection.py
    traffic_iperf.py
    poe.py
    sfp.py
  ui/
    console.py
    progress.py
  storage/
    sqlite.py
    schema.sql
  reports/
    html.py
    csv.py
```

The exact file names may change during implementation, but these boundaries
should stay stable.

## Interface Sketch

These names are guidance for the scaffold, not final API law.

```python
class CommandTransport:
    def open(self) -> None: ...
    def close(self) -> None: ...
    def write(self, data: bytes) -> None: ...
    def read_until_idle(self, timeout: float) -> bytes: ...


class DeviceSession:
    def login(self, credentials) -> bool: ...
    def run_command(self, command: str, timeout: float) -> "CommandResult": ...


class DeviceDetector:
    def detect(self, session: DeviceSession) -> "DeviceIdentity | None": ...


class DeviceAdapter:
    profile: "DeviceProfile"
    def get_identity(self, session: DeviceSession) -> "DeviceIdentity": ...
    def list_ports(self, session: DeviceSession) -> list["PortInfo"]: ...
    def get_mac_table(self, session: DeviceSession) -> list["MacEntry"]: ...
    def get_counters(self, session: DeviceSession, port: "PortInfo") -> "PortCounters": ...
    def shutdown_port(self, session: DeviceSession, port: "PortInfo") -> None: ...


class TestStep:
    def run(self, context: "TestContext") -> "StepResult": ...
```

## Scaling Rules

- No vendor command strings in UI code.
- No raw CLI parsing inside reports.
- No transport-specific code in device adapters except through transport/session
  interfaces.
- New vendors are added through `devices/<vendor>/`.
- New device classes should reuse transport/session/storage/reporting.
- Unknown or partially supported capabilities should produce WARN/unsupported,
  not crashes.
- A test step may require a capability; if missing, it must skip with a clear
  reason.

## MVP Order

1. Architecture and scaffold.
2. Serial transport.
3. CLI session: login, prompt, paging.
4. Device discovery.
5. D-Link profiles and parsers.
6. Normalized port model.
7. Walk-test engine.
8. Active port detection.
9. iperf traffic test.
10. Reports/history.
11. PoE/SFP/final reset and packaging.

## Done for Issue #1

- Architecture document exists.
- Core layers and boundaries are described.
- D-Link is treated as the first adapter, not as hardcoded core logic.
- Future console-controlled devices have a clear extension path.
