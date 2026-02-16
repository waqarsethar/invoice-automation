#!/usr/bin/env python3
"""CLI entry point for the invoice processing pipeline."""

import argparse
import logging
import sys

from src.config_loader import load_config
from src.database import DatabaseLoader
from src.email_monitor import EmailMonitor
from src.logging_setup import setup_logging
from src.metrics import start_metrics_server
from src.notifier import SlackNotifier
from src.pdf_parser import PDFParser
from src.pipeline import InvoicePipeline
from src.validator import InvoiceValidator


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        Parsed arguments namespace.
    """
    parser = argparse.ArgumentParser(
        description="Run the invoice processing pipeline",
    )
    parser.add_argument(
        "--config",
        default="config/config.yaml",
        help="Path to YAML config file (default: config/config.yaml)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without database writes or notifications",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default=None,
        help="Override log level from config",
    )
    return parser.parse_args()


def main() -> int:
    """Main entry point for the invoice pipeline.

    Returns:
        Exit code (0 for success, 1 for failure).
    """
    args = parse_args()

    # Load configuration
    config = load_config(args.config)

    if args.dry_run:
        config.dry_run = True

    if args.log_level:
        config.logging.level = args.log_level

    # Setup logging
    logger = setup_logging(config.logging)
    logger.info("Invoice pipeline starting")
    logger.info("Config loaded from: %s", args.config)

    if config.dry_run:
        logger.info("Running in DRY RUN mode")

    # Start metrics server if enabled
    if config.metrics.enabled:
        start_metrics_server(config.metrics.port)

    # Initialize components
    email_monitor = EmailMonitor(config.email)
    pdf_parser = PDFParser()
    validator = InvoiceValidator(config.validation)
    db_loader = DatabaseLoader(config.database)
    notifier = SlackNotifier(config.slack)

    # Build and run pipeline
    pipeline = InvoicePipeline(
        email_monitor=email_monitor,
        pdf_parser=pdf_parser,
        validator=validator,
        db_loader=db_loader,
        notifier=notifier,
        dry_run=config.dry_run,
    )

    try:
        results = pipeline.run()
        successful = sum(1 for r in results if r.is_success)
        logger.info(
            "Pipeline complete: %d/%d successful", successful, len(results)
        )
        return 0
    except Exception:
        logger.exception("Pipeline failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
