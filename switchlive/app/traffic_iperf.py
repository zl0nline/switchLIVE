"""iperf3 traffic test probe (#10).

Запускает iperf3-клиент через subprocess, парсит результат.
Не зависит от вендора — отдельный probe, используется WalkTestEngine.

Логика:
1. Проверить доступность iperf-сервера (config или ручной ввод).
2. Запустить iperf3 client → собрать вывод.
3. Распарсить throughput, jitter, lost.
4. Конвертировать в OK / WARN / FAIL.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from dataclasses import dataclass

from switchlive.core.errors import TestError

log = logging.getLogger(__name__)

# Пороги по умолчанию
DEFAULT_MIN_THROUGHPUT_MBPS = 50.0  # ниже = WARN
DEFAULT_MAX_LOSS_PERCENT = 5.0  # больше = WARN
FAIL_NO_LINK = 0.0  # 0 Mbps = FAIL


@dataclass
class IperfConfig:
    """Конфигурация iperf-теста."""

    server_host: str = ""
    server_port: int = 5201
    duration_sec: int = 10
    parallel_streams: int = 4
    # Пороги
    min_throughput_mbps: float = DEFAULT_MIN_THROUGHPUT_MBPS
    max_loss_percent: float = DEFAULT_MAX_LOSS_PERCENT
    # Таймаут процесса (сек)
    timeout: int = 30


@dataclass
class IperfResult:
    """Результат iperf-теста."""

    success: bool = False
    throughput_mbps: float = 0.0
    jitter_ms: float = 0.0
    lost_packets: int = 0
    total_packets: int = 0
    loss_percent: float = 0.0
    verdict: str = "SKIP"  # PASS, WARN, FAIL, SKIP
    error: str = ""
    raw_output: str = ""


def check_iperf3_available() -> bool:
    """Проверить, что iperf3 установлен и доступен."""
    return shutil.which("iperf3") is not None


def check_server_reachable(host: str, port: int = 5201, timeout: float = 3.0) -> bool:
    """Проверить доступность iperf-сервера (TCP connect)."""
    import socket

    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (OSError, socket.error):
        return False


def run_iperf_test(config: IperfConfig) -> IperfResult:
    """Запустить iperf3-клиент и вернуть результат.

    Raises TestError если iperf3 не установлен.
    """
    if not config.server_host:
        return IperfResult(
            success=False,
            verdict="SKIP",
            error="IP iperf-сервера не задан",
        )

    if not check_iperf3_available():
        raise TestError(
            "iperf3 не установлен. Установите: apt install iperf3"
        )

    cmd = [
        "iperf3",
        "-c", config.server_host,
        "-p", str(config.server_port),
        "-t", str(config.duration_sec),
        "-J",  # JSON output для парсинга
    ]
    if config.parallel_streams > 1:
        cmd.extend(["-P", str(config.parallel_streams)])

    log.info("Running iperf3: %s", " ".join(cmd))

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=config.timeout,
        )
    except subprocess.TimeoutExpired:
        return IperfResult(
            success=False,
            verdict="FAIL",
            error=f"iperf3 timeout ({config.timeout}s)",
        )
    except FileNotFoundError:
        return IperfResult(
            success=False,
            verdict="FAIL",
            error="iperf3 не найден",
        )

    if proc.returncode != 0:
        stderr = proc.stderr.strip()
        return IperfResult(
            success=False,
            verdict="FAIL",
            error=f"iperf3 error: {stderr[:200]}",
            raw_output=proc.stdout + proc.stderr,
        )

    return _parse_iperf_json(proc.stdout, config)


def _parse_iperf_json(output: str, config: IperfConfig) -> IperfResult:
    """Распарсить JSON-вывод iperf3."""
    import json

    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        # Fallback: текстовый парсинг
        return _parse_iperf_text(output, config)

    result = IperfResult(success=True, raw_output=output)

    # Через sum_sent / sum_received
    end = data.get("end", {})

    # TCP: sum
    summary = end.get("sum_received") or end.get("sum_sent") or end.get("sum", {})

    if summary:
        bits_per_sec = summary.get("bits_per_second", 0) or summary.get("bits_per_second", 0)
        # Если в sum, может быть bits_per_second напрямую
        if not bits_per_sec:
            bits_per_sec = summary.get("bits_per_second", 0)
        result.throughput_mbps = round(bits_per_sec / 1_000_000, 2)

    # UDP: sum имеет lost/total
    if "sum" in end:
        udp_sum = end.get("sum", {})
        result.lost_packets = udp_sum.get("lost_packets", 0) or 0
        result.total_packets = udp_sum.get("total_packets", 0) or 0
        result.jitter_ms = round(
            udp_sum.get("jitter_ms", 0) or udp_sum.get("mean", 0), 3
        )
        if result.total_packets > 0:
            result.loss_percent = round(
                (result.lost_packets / result.total_packets) * 100, 2
            )

    result.verdict = _evaluate_verdict(result, config)
    return result


def _parse_iperf_text(output: str, config: IperfConfig) -> IperfResult:
    """Fallback парсинг текстового вывода iperf3."""
    result = IperfResult(success=True, raw_output=output)

    # Mbits/sec или Gbits/sec
    match = re.search(
        r"(\d+\.?\d*)\s*(Mbits|Gbits)/sec", output
    )
    if match:
        val = float(match.group(1))
        unit = match.group(2)
        if unit == "Gbits":
            val *= 1000
        result.throughput_mbps = round(val, 2)

    # Lost / Total (UDP)
    match = re.search(r"(\d+)/\s*(\d+)\s*\(", output)
    if match:
        result.lost_packets = int(match.group(1))
        result.total_packets = int(match.group(2))
        if result.total_packets > 0:
            result.loss_percent = round(
                (result.lost_packets / result.total_packets) * 100, 2
            )

    # Jitter
    match = re.search(r"(\d+\.?\d*)\s*ms", output)
    if match:
        result.jitter_ms = float(match.group(1))

    result.verdict = _evaluate_verdict(result, config)
    return result


def _evaluate_verdict(result: IperfResult, config: IperfConfig) -> str:
    """Оценить результат: PASS / WARN / FAIL."""
    if result.throughput_mbps <= 0:
        return "FAIL"

    if result.throughput_mbps < config.min_throughput_mbps:
        return "WARN"

    if result.loss_percent > config.max_loss_percent:
        return "WARN"

    return "PASS"
