"""Prometheus metrics definitions and server setup."""

import logging
from typing import Any

logger = logging.getLogger("invoice_automation.metrics")

try:
    from prometheus_client import (
        Counter,
        Gauge,
        Histogram,
        start_http_server,
    )

    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False

# Module-level metric definitions (no-op stubs if prometheus_client unavailable)
if PROMETHEUS_AVAILABLE:
    INVOICES_PROCESSED = Counter(
        "invoices_processed_total",
        "Total number of invoices processed",
        ["status"],
    )

    INVOICES_PROCESSING_DURATION = Histogram(
        "invoice_processing_duration_seconds",
        "Time spent processing a single invoice",
        buckets=(0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
    )

    EMAIL_FETCH_DURATION = Histogram(
        "email_fetch_duration_seconds",
        "Time spent fetching emails from IMAP",
    )

    PDF_PARSE_DURATION = Histogram(
        "pdf_parse_duration_seconds",
        "Time spent parsing a single PDF",
    )

    VALIDATION_FAILURES = Counter(
        "validation_failures_total",
        "Total number of validation failures",
        ["rule"],
    )

    DB_INSERT_DURATION = Histogram(
        "db_insert_duration_seconds",
        "Time spent inserting an invoice into the database",
    )

    PIPELINE_RUNS = Counter(
        "pipeline_runs_total",
        "Total number of pipeline runs",
        ["outcome"],
    )

    ACTIVE_PIPELINE_RUNS = Gauge(
        "active_pipeline_runs",
        "Number of currently active pipeline runs",
    )

    RETRY_ATTEMPTS = Counter(
        "retry_attempts_total",
        "Total number of retry attempts",
        ["operation"],
    )
else:

    class _NoOpMetric:
        """Stub metric that silently does nothing."""

        def labels(self, *args: Any, **kwargs: Any) -> "_NoOpMetric":
            return self

        def inc(self, amount: float = 1) -> None:
            pass

        def dec(self, amount: float = 1) -> None:
            pass

        def set(self, value: float) -> None:
            pass

        def observe(self, amount: float) -> None:
            pass

    _noop = _NoOpMetric()
    INVOICES_PROCESSED = _noop  # type: ignore[assignment]
    INVOICES_PROCESSING_DURATION = _noop  # type: ignore[assignment]
    EMAIL_FETCH_DURATION = _noop  # type: ignore[assignment]
    PDF_PARSE_DURATION = _noop  # type: ignore[assignment]
    VALIDATION_FAILURES = _noop  # type: ignore[assignment]
    DB_INSERT_DURATION = _noop  # type: ignore[assignment]
    PIPELINE_RUNS = _noop  # type: ignore[assignment]
    ACTIVE_PIPELINE_RUNS = _noop  # type: ignore[assignment]
    RETRY_ATTEMPTS = _noop  # type: ignore[assignment]


def start_metrics_server(port: int = 9090) -> None:
    """Start the Prometheus metrics HTTP server.

    Args:
        port: Port to serve metrics on.
    """
    if not PROMETHEUS_AVAILABLE:
        logger.warning(
            "prometheus_client not installed; metrics server not started"
        )
        return

    logger.info("Starting Prometheus metrics server on port %d", port)
    start_http_server(port)
