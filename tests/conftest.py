"""Shared test fixtures for invoice automation tests."""

from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from src.config_loader import (
    AppConfig,
    DatabaseConfig,
    EmailConfig,
    LoggingConfig,
    RetryConfig,
    SlackConfig,
    ValidationConfig,
)
from src.models import (
    EmailAttachment,
    InvoiceData,
    LineItem,
    ProcessingResult,
    ProcessingStatus,
)


@pytest.fixture
def sample_line_items() -> list[LineItem]:
    """Sample line items for testing."""
    return [
        LineItem(
            description="Widget A",
            quantity=10,
            unit_price=Decimal("25.00"),
            total=Decimal("250.00"),
        ),
        LineItem(
            description="Widget B",
            quantity=5,
            unit_price=Decimal("50.00"),
            total=Decimal("250.00"),
        ),
    ]


@pytest.fixture
def sample_invoice_data(sample_line_items: list[LineItem]) -> InvoiceData:
    """Sample parsed invoice data for testing."""
    return InvoiceData(
        invoice_number="INV-2024-001",
        vendor_name="Acme Corp",
        invoice_date=date(2024, 1, 15),
        due_date=date(2024, 2, 15),
        total_amount=Decimal("500.00"),
        currency="USD",
        po_number="PO-2024-100",
        line_items=sample_line_items,
        raw_text="Invoice Number: INV-2024-001\nVendor: Acme Corp\nTotal: $500.00",
    )


@pytest.fixture
def sample_attachment() -> EmailAttachment:
    """Sample email attachment for testing."""
    return EmailAttachment(
        filename="invoice_001.pdf",
        content=b"%PDF-1.4 fake pdf content",
        email_subject="Invoice from Acme Corp",
        email_from="billing@acme.com",
        email_date=datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
        email_uid="12345",
    )


@pytest.fixture
def sample_processing_result(
    sample_attachment: EmailAttachment,
) -> ProcessingResult:
    """Sample processing result for testing."""
    return ProcessingResult(
        attachment=sample_attachment,
        status=ProcessingStatus.PENDING,
    )


@pytest.fixture
def sample_config() -> AppConfig:
    """Sample application configuration for testing."""
    return AppConfig(
        email=EmailConfig(
            imap_host="imap.test.com",
            imap_port=993,
            address="test@test.com",
            password="test-password",
            search_subject="Invoice",
            folder="INBOX",
        ),
        database=DatabaseConfig(
            host="localhost",
            port=5432,
            name="test_db",
            user="test_user",
            password="test_password",
        ),
        slack=SlackConfig(
            webhook_url="https://hooks.slack.com/services/TEST/WEBHOOK/URL",
            enabled=True,
        ),
        retry=RetryConfig(
            max_attempts=3,
            base_delay=0.01,  # Fast retries in tests
            max_delay=0.1,
            exponential_base=2.0,
        ),
        validation=ValidationConfig(
            max_invoice_amount=1_000_000.00,
            min_invoice_amount=0.01,
            po_numbers_file="config/po_numbers.csv",
            approved_vendors_file="config/approved_vendors.csv",
            max_invoice_age_days=365,
        ),
        logging=LoggingConfig(level="DEBUG", json_format=False),
    )


@pytest.fixture
def mock_email_monitor() -> MagicMock:
    """Mock email monitor for pipeline tests."""
    monitor = MagicMock()
    monitor.__enter__ = MagicMock(return_value=monitor)
    monitor.__exit__ = MagicMock(return_value=False)
    return monitor


@pytest.fixture
def mock_pdf_parser() -> MagicMock:
    """Mock PDF parser for pipeline tests."""
    return MagicMock()


@pytest.fixture
def mock_validator() -> MagicMock:
    """Mock validator for pipeline tests."""
    return MagicMock()


@pytest.fixture
def mock_db_loader() -> MagicMock:
    """Mock database loader for pipeline tests."""
    loader = MagicMock()
    loader.__enter__ = MagicMock(return_value=loader)
    loader.__exit__ = MagicMock(return_value=False)
    return loader


@pytest.fixture
def mock_notifier() -> MagicMock:
    """Mock Slack notifier for pipeline tests."""
    return MagicMock()


SAMPLE_PDF_TEXT = """
INVOICE

Invoice Number: INV-2024-001
Date: 01/15/2024
Due Date: 02/15/2024

Vendor: Acme Corp
PO Number: PO-2024-100

Description          Qty    Unit Price    Amount
Widget A              10       $25.00    $250.00
Widget B               5       $50.00    $250.00

                              Total:    $500.00
"""
