-- Схема БД switchLIVE
-- Не D-Link специфичная — общая для всех устройств

CREATE TABLE IF NOT EXISTS devices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    serial TEXT NOT NULL UNIQUE,
    vendor TEXT NOT NULL,
    model TEXT NOT NULL,
    firmware TEXT,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS test_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id INTEGER NOT NULL REFERENCES devices(id),
    started_at TEXT NOT NULL,
    finished_at TEXT,
    operator TEXT,
    overall_verdict TEXT,
    comments TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS port_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES test_runs(id),
    port_index INTEGER NOT NULL,
    port_name TEXT NOT NULL,
    link_up INTEGER,
    speed_actual INTEGER,
    duplex TEXT,
    crc_errors INTEGER,
    drops INTEGER,
    flaps INTEGER,
    iperf_throughput REAL,
    poe_status TEXT,
    poe_class TEXT,
    sfp_vendor TEXT,
    sfp_serial TEXT,
    sfp_rx_power REAL,
    sfp_tx_power REAL,
    sfp_temp REAL,
    verdict TEXT NOT NULL,
    notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_port_results_run ON port_results(run_id);
CREATE INDEX IF NOT EXISTS idx_test_runs_device ON test_runs(device_id);
CREATE INDEX IF NOT EXISTS idx_devices_serial ON devices(serial);
