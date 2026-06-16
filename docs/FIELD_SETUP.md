# Field setup

This guide prepares a fresh Linux workbench for switchLIVE.

## Control host

Use a laptop or mini PC connected to the switch console port through a USB-serial
adapter.

### System packages

Debian/Ubuntu:

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip iperf3
```

Fedora:

```bash
sudo dnf install -y git python3 python3-pip iperf3
```

Python 3.10 or newer is required.

### Serial permissions

Most USB console adapters appear as `/dev/ttyUSB0` or `/dev/ttyACM0`.
Add your user to the serial group, then log out and back in:

```bash
sudo usermod -aG dialout "$USER"
```

If the port still cannot be opened:

```bash
ls -l /dev/ttyUSB* /dev/ttyACM* 2>/dev/null
dmesg | tail -50
```

Common symptoms:

- `Permission denied`: user is not in `dialout`, or the session was not restarted.
- `No such file`: adapter was not detected or uses a different device name.
- Empty console output: wrong baudrate, wrong cable, or the switch is still booting.

### Install switchLIVE

```bash
git clone https://github.com/zl0nline/switchLIVE.git
cd switchLIVE
python3 -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev]"
```

Run:

```bash
switchlive
```

or:

```bash
python -m switchlive
```

## Config files

Start from the examples:

```bash
cp configs/switchlive.example.json switchlive.json
cp configs/standart_login.example.txt standart_login.txt
```

Edit `switchlive.json` for the workbench:

- `serial.default_baudrates`: baudrates tried during discovery.
- `standard_login_file`: path to standard credentials.
- `iperf.server_host`: test host IP.
- `reports.report_dir`: where HTML/CSV reports are written.
- `reports.db_path`: SQLite history database path.
- `timeouts.link_sec`: normal link/test wait.
- `timeouts.poe_sec`: PoE camera boot wait.

Keep real credentials outside git.

## Test host

Use a second host on the test network for traffic checks.

Install iperf3:

```bash
sudo apt install -y iperf3
```

Start the server:

```bash
iperf3 -s
```

The control host must reach TCP port `5201` on the test host:

```bash
iperf3 -c <TEST_HOST_IP> -t 5
```

If the connection fails:

- Check both hosts are in the expected VLAN/subnet.
- Check local firewall rules.
- Verify the switch port under test is connected to the test path.

## PoE camera mode

PoE verification can wait for a camera or powered device to boot.

Expected setup:

- Camera is powered from the switch port under test.
- Camera IP is reachable from the control host.
- Camera answers on TCP port `80`.

If no camera IP is configured, switchLIVE checks PoE power status only.

## Reports and history

Each completed run can be saved to:

- SQLite history database for repeated serial-number lookup.
- HTML report for human review.
- CSV report for spreadsheets or imports.

Reports are generated before any optional factory reset.

## Debug mode and bug reports

Use debug mode when a field run behaves unexpectedly:

```bash
switchlive --debug
```

Debug mode writes verbose logs to `logs/switchlive-YYYYMMDD-HHMMSS.log`,
including console TX/RX chunks with common secrets masked.

To collect files for a bug report:

```bash
switchlive --debug --bug-report
```

or choose `Собрать debug bundle` in the console menu. The bundle is written to
`debug-bundles/` and includes:

- environment summary;
- sanitized config;
- current debug log;
- recent HTML/CSV reports.

Passwords, enable passwords, tokens and API keys are masked before writing the
bundle. Keep real credential files outside git and do not attach them manually.

## Windows notes

The current MVP targets Linux workbenches. The code avoids Linux-only packaging
assumptions where practical, so a later Windows package can map:

- COM ports instead of `/dev/ttyUSB*`.
- Windows iperf3 binary in `PATH`.
- A user-writable report/history directory.
