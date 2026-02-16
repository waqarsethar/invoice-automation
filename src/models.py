"""Data models and enumerations for invoice processing."""

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum


class ProcessingStatus(str, Enum):
    """Status of an invoice processing attempt."""

    PENDING = "pending"
    FETCHED = "fetched"
    PARSED = "parsed"
    VALIDATED = "validated"
    VALIDATION_FAILED = "validation_failed"
    STORED = "stored"
    NOTIFIED = "notified"
    FAILED = "failed"
    DUPLICATE = "duplicate"


class NotificationType(str, Enum):
    """Type of Slack notification to send."""

    SUCCESS = "success"
    FAILURE = "failure"
    SUMMARY = "summary"
    WARNING = "warning"


@dataclass(frozen=True)
class LineItem:
    """A single line item on an invoice.

    Args:
        description: Item description.
        quantity: Number of units.
        unit_price: Price per unit.
        total: Total amount for this line item.
    """

    description: str
    quantity: int
    unit_price: Decimal
    total: Decimal


@dataclass
class InvoiceData:
    """Extracted and structured invoice data.

    Args:
        invoice_number: Unique invoice identifier.
        vendor_name: Name of the vendor/supplier.
        invoice_date: Date the invoice was issued.
        due_date: Payment due date.
        total_amount: Total invoice amount.
        currency: Currency code (default USD).
        vendor_email: Vendor contact email address.
        subtotal: Subtotal before tax.
        tax: Tax amount.
        po_number: Associated purchase order number.
        line_items: Individual line items on the invoice.
        raw_text: Original extracted text from the PDF.
    """

    invoice_number: str
    vendor_name: str
    invoice_date: date
    due_date: date | None
    total_amount: Decimal
    currency: str = "USD"
    vendor_email: str | None = None
    subtotal: Decimal = Decimal("0")
    tax: Decimal = Decimal("0")
    po_number: str | None = None
    line_items: list[LineItem] = field(default_factory=list)
    raw_text: str = ""

    def __post_init__(self) -> None:
        """Validate data after initialization."""
        if self.total_amount <= 0:
            raise ValueError("Invoice total must be positive")
        if not self.invoice_number:
            raise ValueError("Invoice number is required")


@dataclass(frozen=True)
class EmailAttachment:
    """An email attachment containing an invoice PDF.

    Args:
        filename: Original filename of the attachment.
        content: Raw bytes of the PDF file.
        email_subject: Subject line of the source email.
        email_from: Sender address of the source email.
        email_date: Date the email was received.
        email_uid: IMAP UID for marking as processed.
        content_type: MIME content type of the attachment.
        size_bytes: Size of the attachment in bytes.
    """

    filename: str
    content: bytes
    email_subject: str
    email_from: str
    email_date: datetime
    email_uid: str
    content_type: str = "application/pdf"
    size_bytes: int = 0


@dataclass
class ValidationResult:
    """Result of validating an invoice against business rules.

    Args:
        is_valid: Whether all validation checks passed.
        errors: List of validation error messages.
        warnings: List of validation warning messages.
        matched_po: Matched purchase order number (if any).
        confidence_score: Confidence score from 0.0 to 1.0.
    """

    is_valid: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    matched_po: str | None = None
    confidence_score: float = 1.0

    def add_error(self, message: str) -> None:
        """Add a validation error and mark result as invalid.

        Args:
            message: Error description.
        """
        self.errors.append(message)
        self.is_valid = False

    def add_warning(self, message: str) -> None:
        """Add a validation warning (does not affect validity).

        Args:
            message: Warning description.
        """
        self.warnings.append(message)


@dataclass
class ProcessingResult:
    """Mutable accumulator tracking the processing state of a single invoice.

    Args:
        attachment: The source email attachment.
        status: Current processing status.
        invoice_data: Extracted invoice data (populated after parsing).
        validation_errors: List of validation failure messages.
        error_message: Error message if processing failed.
        processing_started_at: Timestamp when processing began.
        processing_completed_at: Timestamp when processing finished.
    """

    attachment: EmailAttachment
    status: ProcessingStatus = ProcessingStatus.PENDING
    invoice_data: InvoiceData | None = None
    validation_errors: list[str] = field(default_factory=list)
    error_message: str | None = None
    processing_started_at: datetime | None = None
    processing_completed_at: datetime | None = None

    @property
    def is_success(self) -> bool:
        """Whether the invoice was processed successfully."""
        return self.status in (ProcessingStatus.STORED, ProcessingStatus.NOTIFIED)

    @property
    def is_terminal(self) -> bool:
        """Whether processing has reached a terminal state."""
        return self.status in (
            ProcessingStatus.STORED,
            ProcessingStatus.NOTIFIED,
            ProcessingStatus.FAILED,
            ProcessingStatus.VALIDATION_FAILED,
            ProcessingStatus.DUPLICATE,
        )


@dataclass
class PipelineResult:
    """Pipeline execution result.

    Args:
        total_emails: Total number of emails processed.
        processed: Number of successfully processed invoices.
        failed: Number of failed invoices.
        errors: List of error messages from the run.
        execution_time_seconds: Total pipeline execution time.
    """

    total_emails: int
    processed: int
    failed: int
    errors: list[str] = field(default_factory=list)
    execution_time_seconds: float = 0.0
