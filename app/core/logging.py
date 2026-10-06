"""
Structured logging setup.
IMPORTANT: The API key and any secrets MUST NEVER appear in logs.
"""
from __future__ import annotations

import logging
import sys
from datetime import date
from pathlib import Path


def _get_log_file_path() -> Path:
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)
    today = date.today().isoformat()
    return logs_dir / f"app_{today}.log"


class SensitiveDataFilter(logging.Filter):
    """
    Log filter that redacts any accidentally-logged sensitive data.
    Removes API keys even if someone accidentally logs a URL with the key.
    """

    REDACT_PATTERNS = [
        "api_key",
        "password",
        "token",
        "authorization",
        "secret",
    ]

    def filter(self, record: logging.LogRecord) -> bool:
        msg = str(record.getMessage()).lower()
        for pattern in self.REDACT_PATTERNS:
            if pattern in msg:
                record.msg = "[REDACTED - sensitive data detected in log message]"
                record.args = ()
                break
        return True


def setup_logging(log_level: str = "INFO") -> None:
    """Configure application-wide logging with file and console handlers."""
    level = getattr(logging, log_level.upper(), logging.INFO)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Sensitive data filter applied to ALL handlers
    sensitive_filter = SensitiveDataFilter()

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(sensitive_filter)

    # File handler (rotates daily by filename)
    try:
        file_handler = logging.FileHandler(
            _get_log_file_path(), encoding="utf-8"
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        file_handler.addFilter(sensitive_filter)
    except OSError as e:
        print(f"Warning: Could not create log file: {e}", file=sys.stderr)
        file_handler = None

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Clear any existing handlers
    root_logger.handlers.clear()

    root_logger.addHandler(console_handler)
    if file_handler:
        root_logger.addHandler(file_handler)

    # Suppress noisy third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Return a logger for the given module name."""
    return logging.getLogger(name)
