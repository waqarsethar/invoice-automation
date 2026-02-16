"""Custom exception hierarchy for the invoice automation system."""


class InvoiceAutomationError(Exception):
    """Base exception for all invoice automation errors.

    Args:
        message: Human-readable error description.
        details: Optional dict with additional context.
    """

    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class EmailConnectionError(InvoiceAutomationError):
    """Raised when email server connection or authentication fails."""


class PDFExtractionError(InvoiceAutomationError):
    """Raised when PDF text extraction or parsing fails."""


class ValidationError(InvoiceAutomationError):
    """Raised when invoice data fails business rule validation."""


class DatabaseError(InvoiceAutomationError):
    """Raised when database operations fail."""


class NotificationError(InvoiceAutomationError):
    """Raised when sending notifications fails."""


class RetryExhaustedError(InvoiceAutomationError):
    """Raised when all retry attempts have been exhausted.

    Args:
        message: Human-readable error description.
        attempts: Number of attempts made.
        last_exception: The final exception that caused the last failure.
        details: Optional dict with additional context.
    """

    def __init__(
        self,
        message: str,
        attempts: int,
        last_exception: Exception,
        details: dict | None = None,
    ) -> None:
        super().__init__(message, details)
        self.attempts = attempts
        self.last_exception = last_exception
