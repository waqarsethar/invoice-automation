"""Logging configuration with JSON formatting and rotating file handlers."""

import json
import logging
import sys
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

from src.config_loader import LoggingConfig


class JsonFormatter(logging.Formatter):
    """Formats log records as JSON lines.

    Produces structured JSON output with timestamp, level, logger name,
    message, and any extra fields attached to the record.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format a log record as a JSON string.

        Args:
            record: The log record to format.

        Returns:
            JSON-formatted log string.
        """
        log_entry = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        if record.exc_info and record.exc_info[1] is not None:
            log_entry["exception"] = self.formatException(record.exc_info)

        # Include extra fields
        for key in ("invoice_number", "vendor", "email_uid", "duration_ms"):
            value = getattr(record, key, None)
            if value is not None:
                log_entry[key] = value

        return json.dumps(log_entry)


def setup_logging(config: LoggingConfig | None = None) -> logging.Logger:
    """Configure application-wide logging.

    Sets up a root logger with both console and rotating file handlers.
    Uses JSON formatting when configured.

    Args:
        config: Logging configuration. Uses defaults if None.

    Returns:
        Configured root logger instance.
    """
    if config is None:
        config = LoggingConfig()

    log_dir = Path(config.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger("invoice_automation")
    root_logger.setLevel(getattr(logging, config.level.upper(), logging.INFO))
    root_logger.handlers.clear()

    if config.json_format:
        formatter = JsonFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # Rotating file handler
    file_handler = RotatingFileHandler(
        log_dir / "invoice_automation.log",
        maxBytes=config.max_bytes,
        backupCount=config.backup_count,
    )
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    return root_logger
