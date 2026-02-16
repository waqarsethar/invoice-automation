"""Invoice processing pipeline orchestrator."""

import logging
import time
from datetime import datetime, timezone

from src.database import DatabaseLoader
from src.email_monitor import EmailMonitor
from src.exceptions import (
    DatabaseError,
    NotificationError,
    PDFExtractionError,
    RetryExhaustedError,
)
from src.metrics import (
    ACTIVE_PIPELINE_RUNS,
    INVOICES_PROCESSED,
    INVOICES_PROCESSING_DURATION,
    PIPELINE_RUNS,
    VALIDATION_FAILURES,
)
from src.models import EmailAttachment, ProcessingResult, ProcessingStatus, ValidationResult
from src.notifier import SlackNotifier
from src.pdf_parser import PDFParser
from src.validator import InvoiceValidator

logger = logging.getLogger("invoice_automation.pipeline")


class InvoicePipeline:
    """Orchestrates the full invoice processing workflow.

    Coordinates: email fetch → PDF parse → validate → store → notify.
    Uses dependency injection for all components to enable testing.

    Args:
        email_monitor: Email inbox monitor for fetching attachments.
        pdf_parser: PDF text extractor and parser.
        validator: Business rule validator.
        db_loader: Database loader for invoice storage.
        notifier: Slack notification sender.
        dry_run: If True, skip database writes and notifications.
    """

    def __init__(
        self,
        email_monitor: EmailMonitor,
        pdf_parser: PDFParser,
        validator: InvoiceValidator,
        db_loader: DatabaseLoader,
        notifier: SlackNotifier,
        dry_run: bool = False,
    ) -> None:
        self._email_monitor = email_monitor
        self._pdf_parser = pdf_parser
        self._validator = validator
        self._db_loader = db_loader
        self._notifier = notifier
        self._dry_run = dry_run

    def run(self) -> list[ProcessingResult]:
        """Execute the full invoice processing pipeline.

        Fetches invoice emails, processes each attachment through
        parse → validate → store → notify stages. Errors in one
        invoice do not affect processing of others.

        Returns:
            List of ProcessingResult for each attachment processed.
        """
        ACTIVE_PIPELINE_RUNS.inc()
        run_start = time.monotonic()
        results: list[ProcessingResult] = []

        try:
            logger.info("Starting invoice processing pipeline run")

            with self._email_monitor as monitor:
                attachments = monitor.fetch_invoice_emails()

            if not attachments:
                logger.info("No invoice attachments found")
                PIPELINE_RUNS.labels(outcome="empty").inc()
                return results

            logger.info("Processing %d attachment(s)", len(attachments))

            with self._db_loader as db:
                for attachment in attachments:
                    result = self._process_single(attachment, db)
                    results.append(result)

            self._send_summary(results)

            successful = sum(1 for r in results if r.is_success)
            failed = len(results) - successful
            logger.info(
                "Pipeline run complete: %d processed, %d successful, %d failed",
                len(results),
                successful,
                failed,
            )
            PIPELINE_RUNS.labels(outcome="success").inc()

        except Exception:
            logger.exception("Pipeline run failed with unexpected error")
            PIPELINE_RUNS.labels(outcome="error").inc()
            raise
        finally:
            duration = time.monotonic() - run_start
            ACTIVE_PIPELINE_RUNS.dec()
            logger.info("Pipeline run duration: %.2f seconds", duration)

        return results

    def _process_single(
        self,
        attachment: EmailAttachment,
        db: DatabaseLoader,
    ) -> ProcessingResult:
        """Process a single invoice attachment through all stages.

        Errors are caught per-item so one failure doesn't stop the batch.

        Args:
            attachment: The email attachment to process.
            db: Active database loader connection.

        Returns:
            ProcessingResult tracking the outcome of each stage.
        """
        result = ProcessingResult(
            attachment=attachment,
            processing_started_at=datetime.now(timezone.utc),
        )
        start_time = time.monotonic()

        try:
            # Stage 1: Parse PDF
            result.status = ProcessingStatus.FETCHED
            logger.info(
                "Parsing PDF: %s (from: %s)",
                attachment.filename,
                attachment.email_from,
            )
            invoice_data = self._pdf_parser.parse(
                attachment.content, attachment.filename
            )
            result.invoice_data = invoice_data
            result.status = ProcessingStatus.PARSED

            # Stage 2: Validate
            logger.info(
                "Validating invoice %s", invoice_data.invoice_number
            )
            validation_result = self._validator.validate(invoice_data)

            if not validation_result.is_valid:
                result.status = ProcessingStatus.VALIDATION_FAILED
                result.validation_errors = validation_result.errors
                result.error_message = "; ".join(validation_result.errors)

                for error in validation_result.errors:
                    VALIDATION_FAILURES.labels(rule="business_rule").inc()

                logger.warning(
                    "Invoice %s failed validation: %s",
                    invoice_data.invoice_number,
                    result.error_message,
                )

                if not self._dry_run:
                    self._notify_failure(attachment, result.error_message)

                result.processing_completed_at = datetime.now(timezone.utc)
                INVOICES_PROCESSED.labels(status="validation_failed").inc()
                return result

            result.status = ProcessingStatus.VALIDATED

            # Stage 3: Check duplicate and store
            if not self._dry_run:
                if db.check_duplicate(invoice_data.invoice_number):
                    result.status = ProcessingStatus.DUPLICATE
                    result.error_message = (
                        f"Duplicate invoice: {invoice_data.invoice_number}"
                    )
                    logger.warning(result.error_message)
                    INVOICES_PROCESSED.labels(status="duplicate").inc()
                    result.processing_completed_at = datetime.now(timezone.utc)
                    return result

                db.insert_invoice(
                    invoice_data,
                    email_from=attachment.email_from,
                    email_subject=attachment.email_subject,
                )
                result.status = ProcessingStatus.STORED

                # Stage 4: Notify success
                if self._notify_success(invoice_data):
                    result.status = ProcessingStatus.NOTIFIED
            else:
                result.status = ProcessingStatus.STORED
                logger.info(
                    "[DRY RUN] Would store invoice %s",
                    invoice_data.invoice_number,
                )

            # Mark email as processed
            try:
                with self._email_monitor as monitor:
                    monitor.mark_as_processed(attachment.email_uid)
            except Exception:
                logger.warning(
                    "Failed to mark email as processed (UID: %s)",
                    attachment.email_uid,
                    exc_info=True,
                )

            INVOICES_PROCESSED.labels(status="success").inc()

        except PDFExtractionError as exc:
            result.status = ProcessingStatus.FAILED
            result.error_message = str(exc)
            logger.error(
                "PDF extraction failed for %s: %s",
                attachment.filename,
                exc,
            )
            INVOICES_PROCESSED.labels(status="parse_error").inc()

            if not self._dry_run:
                self._notify_failure(attachment, str(exc))

        except (DatabaseError, RetryExhaustedError) as exc:
            result.status = ProcessingStatus.FAILED
            result.error_message = str(exc)
            logger.error(
                "Database error for %s: %s",
                attachment.filename,
                exc,
            )
            INVOICES_PROCESSED.labels(status="db_error").inc()

        except Exception as exc:
            result.status = ProcessingStatus.FAILED
            result.error_message = f"Unexpected error: {exc}"
            logger.exception(
                "Unexpected error processing %s", attachment.filename
            )
            INVOICES_PROCESSED.labels(status="unexpected_error").inc()

        finally:
            duration = time.monotonic() - start_time
            result.processing_completed_at = datetime.now(timezone.utc)
            INVOICES_PROCESSING_DURATION.observe(duration)
            logger.info(
                "Processed %s in %.2f seconds (status: %s)",
                attachment.filename,
                duration,
                result.status.value,
            )

        return result

    def _notify_success(self, invoice_data: object) -> bool:
        """Send success notification, swallowing errors.

        Args:
            invoice_data: The processed invoice data.

        Returns:
            True if notification was sent successfully, False otherwise.
        """
        try:
            self._notifier.notify_success(invoice_data)  # type: ignore[arg-type]
            return True
        except NotificationError:
            logger.warning(
                "Failed to send success notification", exc_info=True
            )
            return False

    def _notify_failure(
        self, attachment: EmailAttachment, error_message: str
    ) -> None:
        """Send failure notification, swallowing errors.

        Args:
            attachment: The failed attachment.
            error_message: Error description.
        """
        try:
            self._notifier.notify_failure(
                attachment.filename,
                error_message,
                attachment.email_from,
            )
        except NotificationError:
            logger.warning(
                "Failed to send failure notification", exc_info=True
            )

    def _send_summary(self, results: list[ProcessingResult]) -> None:
        """Send pipeline run summary notification.

        Args:
            results: All processing results from this run.
        """
        if self._dry_run or not results:
            return

        try:
            self._notifier.notify_summary(results)
        except NotificationError:
            logger.warning(
                "Failed to send summary notification", exc_info=True
            )
