"""Debug logging and diagnostic bundle helpers."""

from __future__ import annotations

import json
import logging
import platform
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

from switchlive.config import Config

SECRET_KEYS = ("password", "secret", "token", "key", "credential")
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


@dataclass
class DebugContext:
    """Runtime debug paths used by the console and bug-report bundle."""

    enabled: bool = False
    log_file: Path | None = None
    log_dir: Path = Path("logs")
    bundle_dir: Path = Path("debug-bundles")


class RedactingFormatter(logging.Formatter):
    """Logging formatter that masks credentials in rendered log lines."""

    def format(self, record: logging.LogRecord) -> str:
        return redact_text(super().format(record))


def redact_text(text: str) -> str:
    """Mask common credential patterns in free-form text."""
    patterns = (
        r"(?i)(password[ \t]*[:=][ \t]*)[^\s\r\n]+",
        r"(?i)(enable[_ -]?password[ \t]*[:=][ \t]*)[^\s\r\n]+",
        r"(?i)(secret[ \t]*[:=][ \t]*)[^\s\r\n]+",
        r"(?i)(token[ \t]*[:=][ \t]*)[^\s\r\n]+",
        r"(?i)(api[_ -]?key[ \t]*[:=][ \t]*)[^\s\r\n]+",
        r"(?im)^([ \t]*enable[ \t]+password(?:[ \t]+\d+)?[ \t]+)[^\s\r\n]+",
        r"(?im)^([ \t]*username[ \t]+\S+[ \t]+password(?:[ \t]+\d+)?[ \t]+)[^\s\r\n]+",
        r"(?im)^([ \t]*snmp-server[ \t]+community[ \t]+)[^\s\r\n]+",
        r"(?im)^([ \t]*community[ \t]+)[^\s\r\n]+",
    )
    redacted = text
    for pattern in patterns:
        redacted = re.sub(pattern, r"\1***", redacted)
    return redacted


def sanitize_data(value: Any) -> Any:
    """Recursively mask sensitive values in JSON-like data."""
    if isinstance(value, dict):
        return {
            key: "***" if _is_secret_key(str(key)) else sanitize_data(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [sanitize_data(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value


def configure_logging(
    *,
    debug: bool = False,
    log_dir: str | Path = "logs",
) -> DebugContext:
    """Configure console logging and optional debug log file."""
    context = DebugContext(enabled=debug, log_dir=Path(log_dir))
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.DEBUG)

    console = logging.StreamHandler()
    console.setLevel(logging.INFO if debug else logging.WARNING)
    console.setFormatter(RedactingFormatter(LOG_FORMAT, DATE_FORMAT))
    root.addHandler(console)

    if debug:
        context.log_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        context.log_file = context.log_dir / f"switchlive-{stamp}.log"
        file_handler = logging.FileHandler(context.log_file, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(RedactingFormatter(LOG_FORMAT, DATE_FORMAT))
        root.addHandler(file_handler)
        logging.getLogger(__name__).info("Debug log enabled: %s", context.log_file)

    return context


def collect_debug_bundle(
    *,
    config: Config,
    config_path: str | Path | None = None,
    context: DebugContext | None = None,
    output_dir: str | Path = "debug-bundles",
) -> Path:
    """Create a zip with sanitized config, logs, reports and environment info."""
    ctx = context or DebugContext()
    bundle_dir = Path(output_dir)
    bundle_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    bundle_path = bundle_dir / f"switchlive-debug-{stamp}.zip"

    with ZipFile(bundle_path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("environment.txt", _environment_text())
        archive.writestr(
            "config.sanitized.json",
            json.dumps(_sanitized_config(config, config_path), ensure_ascii=False, indent=2),
        )
        _write_text_file(archive, ctx.log_file, "logs")
        _write_recent_files(archive, Path(config.report_dir), "reports", ("*.html", "*.csv"))

    logging.getLogger(__name__).info("Debug bundle created: %s", bundle_path)
    return bundle_path


def _sanitized_config(config: Config, config_path: str | Path | None) -> dict[str, Any]:
    data = {
        "config_path": str(config_path) if config_path else "",
        "config": sanitize_data(config.__dict__),
    }
    path = Path(config_path) if config_path else None
    if path and path.exists():
        try:
            data["source_config"] = sanitize_data(json.loads(path.read_text(encoding="utf-8")))
        except Exception as exc:
            data["source_config_error"] = str(exc)
    return data


def _write_text_file(archive: ZipFile, path: Path | None, prefix: str) -> None:
    if not path or not path.exists() or not path.is_file():
        return
    data = redact_text(path.read_text(encoding="utf-8", errors="replace"))
    archive.writestr(f"{prefix}/{path.name}", data)


def _write_recent_files(
    archive: ZipFile,
    directory: Path,
    prefix: str,
    patterns: tuple[str, ...],
    limit: int = 10,
) -> None:
    if not directory.exists() or not directory.is_dir():
        return
    files: list[Path] = []
    for pattern in patterns:
        files.extend(directory.glob(pattern))
    for path in sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)[:limit]:
        if path.is_file():
            data = redact_text(path.read_text(encoding="utf-8", errors="replace"))
            archive.writestr(f"{prefix}/{path.name}", data)


def _environment_text() -> str:
    return "\n".join(
        [
            f"python={sys.version.split()[0]}",
            f"platform={platform.platform()}",
            f"executable={sys.executable}",
        ]
    )


def _is_secret_key(key: str) -> bool:
    lowered = key.lower()
    return any(part in lowered for part in SECRET_KEYS)
