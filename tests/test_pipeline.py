"""Tests for the invoice pipeline orchestrator."""

from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from src.exceptions import (
    DatabaseError,
    NotificationError,
    PDFExtractionError,
)
from src.models import (
    EmailAttachment,
    InvoiceData,
    LineItem,
    ProcessingStatus,
)
from src.pipeline import InvoicePipeline
from src.models import ValidationResult


@pytest.fixture
def attachment() -> EmailAttachment:
    """Sample attachment for pipeline tests."""
    return EmailAttachment(
        filename="invoice.pdf",
        content=b"%PDF-test",
        email_subject="Invoice from Acme",
        email_from="billing@acme.com",
        email_date=datetime(2024, 1, 15, tzinfo=timezone.utc),
        email_uid="100",
    )


@pytest.fixture
def invoice_data() -> InvoiceData:
    """Sample parsed invoice data."""
    return InvoiceData(
        invoice_number="INV-2024-001",
        vendor_name="Acme Corp",
        invoice_date=date(2024, 1, 15),
        due_date=date(2024, 2, 15),
        total_amount=Decimal("500.00"),
        po_number="PO-2024-100",
        line_items=[
            LineItem("Widget", 10, Decimal("50.00"), Decimal("500.00")),
        ],
    )


@pytest.fixture
def pipeline(
    mock_email_monitor: MagicMock,
    mock_pdf_parser: MagicMock,
    mock_validator: MagicMock,
    mock_db_loader: MagicMock,
    mock_notifier: MagicMock,
) -> InvoicePipeline:
    """Pipeline with all mocked dependencies."""
    return InvoicePipeline(
        email_monitor=mock_email_monitor,
        pdf_parser=mock_pdf_parser,
        validator=mock_validator,
        db_loader=mock_db_loader,
        notifier=mock_notifier,
    )


class TestPipelineHappyPath:
    """Tests for successful processing."""

    def test_full_success(
        self,
        pipeline: InvoicePipeline,
        mock_email_monitor: MagicMock,
        mock_pdf_parser: MagicMock,
        mock_validator: MagicMock,
        mock_db_loader: MagicMock,
        mock_notifier: MagicMock,
        attachment: EmailAttachment,
        invoice_data: InvoiceData,
    ) -> None:
        """Happy path: fetch → parse → validate → store → notify."""
        mock_email_monitor.fetch_invoice_emails.return_value = [attachment]
        mock_pdf_parser.parse.return_value = invoice_data
        mock_validator.validate.return_value = ValidationResult(is_valid=True)
        mock_db_loader.check_duplicate.return_value = False
        mock_db_loader.insert_invoice.return_value = "record-id"

        results = pipeline.run()

        assert len(results) == 1
        assert results[0].is_success
        assert results[0].invoice_data == invoice_data
        mock_pdf_parser.parse.assert_called_once_with(
            attachment.content, attachment.filename
        )
        mock_validator.validate.assert_called_once_with(invoice_data)
        mock_db_loader.insert_invoice.assert_called_once()
        mock_notifier.notify_success.assert_called_once_with(invoice_data)
        mock_notifier.notify_summary.assert_called_once()

    def test_no_emails(
        self,
        pipeline: InvoicePipeline,
        mock_email_monitor: MagicMock,
    ) -> None:
        """No emails found returns empty results."""
        mock_email_monitor.fetch_invoice_emails.return_value = []

        results = pipeline.run()

        assert results == []


class TestPipelineParseFailure:
    """Tests for PDF parsing failures."""

    def test_parse_failure_continues_batch(
        self,
        pipeline: InvoicePipeline,
        mock_email_monitor: MagicMock,
        mock_pdf_parser: MagicMock,
        mock_notifier: MagicMock,
        attachment: EmailAttachment,
    ) -> None:
        """Parse failure marks result as failed."""
        mock_email_monitor.fetch_invoice_emails.return_value = [attachment]
        mock_pdf_parser.parse.side_effect = PDFExtractionError(
            message="Cannot parse PDF"
        )

        results = pipeline.run()

        assert len(results) == 1
        assert results[0].status == ProcessingStatus.FAILED
        assert "Cannot parse" in results[0].error_message
        mock_notifier.notify_failure.assert_called_once()


class TestPipelineValidationFailure:
    """Tests for validation failures."""

    def test_validation_failure(
        self,
        pipeline: InvoicePipeline,
        mock_email_monitor: MagicMock,
        mock_pdf_parser: MagicMock,
        mock_validator: MagicMock,
        mock_db_loader: MagicMock,
        mock_notifier: MagicMock,
        attachment: EmailAttachment,
        invoice_data: InvoiceData,
    ) -> None:
        """Validation failure skips storage."""
        mock_email_monitor.fetch_invoice_emails.return_value = [attachment]
        mock_pdf_parser.parse.return_value = invoice_data

        validation_result = ValidationResult()
        validation_result.add_error("Amount exceeds maximum")
        mock_validator.validate.return_value = validation_result

        results = pipeline.run()

        assert len(results) == 1
        assert results[0].status == ProcessingStatus.VALIDATION_FAILED
        assert "Amount exceeds" in results[0].error_message
        mock_db_loader.insert_invoice.assert_not_called()
        mock_notifier.notify_failure.assert_called_once()


class TestPipelineDuplicateHandling:
    """Tests for duplicate invoice detection."""

    def test_duplicate_invoice(
        self,
        pipeline: InvoicePipeline,
        mock_email_monitor: MagicMock,
        mock_pdf_parser: MagicMock,
        mock_validator: MagicMock,
        mock_db_loader: MagicMock,
        attachment: EmailAttachment,
        invoice_data: InvoiceData,
    ) -> None:
        """Duplicate invoice is detected and skipped."""
        mock_email_monitor.fetch_invoice_emails.return_value = [attachment]
        mock_pdf_parser.parse.return_value = invoice_data
        mock_validator.validate.return_value = ValidationResult(is_valid=True)
        mock_db_loader.check_duplicate.return_value = True

        results = pipeline.run()

        assert len(results) == 1
        assert results[0].status == ProcessingStatus.DUPLICATE
        mock_db_loader.insert_invoice.assert_not_called()


class TestPipelineNotificationResilience:
    """Tests for notification failure resilience."""

    def test_notification_failure_does_not_fail_pipeline(
        self,
        pipeline: InvoicePipeline,
        mock_email_monitor: MagicMock,
        mock_pdf_parser: MagicMock,
        mock_validator: MagicMock,
        mock_db_loader: MagicMock,
        mock_notifier: MagicMock,
        attachment: EmailAttachment,
        invoice_data: InvoiceData,
    ) -> None:
        """Notification failures don't crash the pipeline."""
        mock_email_monitor.fetch_invoice_emails.return_value = [attachment]
        mock_pdf_parser.parse.return_value = invoice_data
        mock_validator.validate.return_value = ValidationResult(is_valid=True)
        mock_db_loader.check_duplicate.return_value = False
        mock_db_loader.insert_invoice.return_value = "id"
        mock_notifier.notify_success.side_effect = NotificationError(
            message="Slack down"
        )

        results = pipeline.run()

        # Pipeline still succeeds despite notification failure
        assert len(results) == 1
        assert results[0].status == ProcessingStatus.STORED


class TestPipelineDatabaseError:
    """Tests for database error handling."""

    def test_db_error_marks_failed(
        self,
        pipeline: InvoicePipeline,
        mock_email_monitor: MagicMock,
        mock_pdf_parser: MagicMock,
        mock_validator: MagicMock,
        mock_db_loader: MagicMock,
        attachment: EmailAttachment,
        invoice_data: InvoiceData,
    ) -> None:
        """Database error marks result as failed."""
        mock_email_monitor.fetch_invoice_emails.return_value = [attachment]
        mock_pdf_parser.parse.return_value = invoice_data
        mock_validator.validate.return_value = ValidationResult(is_valid=True)
        mock_db_loader.check_duplicate.return_value = False
        mock_db_loader.insert_invoice.side_effect = DatabaseError(
            message="Connection lost"
        )

        results = pipeline.run()

        assert len(results) == 1
        assert results[0].status == ProcessingStatus.FAILED
        assert "Connection lost" in results[0].error_message


class TestPipelineDryRun:
    """Tests for dry-run mode."""

    def test_dry_run_skips_storage_and_notifications(
        self,
        mock_email_monitor: MagicMock,
        mock_pdf_parser: MagicMock,
        mock_validator: MagicMock,
        mock_db_loader: MagicMock,
        mock_notifier: MagicMock,
        attachment: EmailAttachment,
        invoice_data: InvoiceData,
    ) -> None:
        """Dry run skips DB writes and notifications."""
        pipeline = InvoicePipeline(
            email_monitor=mock_email_monitor,
            pdf_parser=mock_pdf_parser,
            validator=mock_validator,
            db_loader=mock_db_loader,
            notifier=mock_notifier,
            dry_run=True,
        )
        mock_email_monitor.fetch_invoice_emails.return_value = [attachment]
        mock_pdf_parser.parse.return_value = invoice_data
        mock_validator.validate.return_value = ValidationResult(is_valid=True)

        results = pipeline.run()

        assert len(results) == 1
        assert results[0].status == ProcessingStatus.STORED
        mock_db_loader.insert_invoice.assert_not_called()
        mock_db_loader.check_duplicate.assert_not_called()
        mock_notifier.notify_success.assert_not_called()
        mock_notifier.notify_summary.assert_not_called()
