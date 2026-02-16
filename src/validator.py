"""Business rule validation for invoice data."""

import csv
import logging
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from src.config_loader import ValidationConfig
from src.models import InvoiceData, ValidationResult

logger = logging.getLogger("invoice_automation.validator")


class InvoiceValidator:
    """Validates invoice data against configurable business rules.

    Loads reference data (PO numbers, approved vendors) from CSV files
    at initialization and validates invoices against six checks:
    1. Invoice number format
    2. Amount range
    3. PO number match
    4. Approved vendor
    5. Line items sum
    6. Date sanity

    Args:
        config: Validation rules configuration.
    """

    def __init__(self, config: ValidationConfig) -> None:
        self._config = config
        self._valid_po_numbers: set[str] = self._load_po_numbers()
        self._approved_vendors: set[str] = self._load_approved_vendors()

    def _load_po_numbers(self) -> set[str]:
        """Load valid PO numbers from CSV file.

        Returns:
            Set of valid PO number strings.
        """
        path = Path(self._config.po_numbers_file)
        if not path.exists():
            logger.warning("PO numbers file not found: %s", path)
            return set()

        po_numbers: set[str] = set()
        with open(path, "r", newline="") as f:
            reader = csv.reader(f)
            next(reader, None)  # Skip header
            for row in reader:
                if row:
                    po_numbers.add(row[0].strip())

        logger.info("Loaded %d valid PO numbers", len(po_numbers))
        return po_numbers

    def _load_approved_vendors(self) -> set[str]:
        """Load approved vendor names from CSV file.

        Returns:
            Set of approved vendor names (lowercased).
        """
        path = Path(self._config.approved_vendors_file)
        if not path.exists():
            logger.warning("Approved vendors file not found: %s", path)
            return set()

        vendors: set[str] = set()
        with open(path, "r", newline="") as f:
            reader = csv.reader(f)
            next(reader, None)  # Skip header
            for row in reader:
                if row:
                    vendors.add(row[0].strip().lower())

        logger.info("Loaded %d approved vendors", len(vendors))
        return vendors

    def validate(self, invoice: InvoiceData) -> ValidationResult:
        """Run all validation checks against an invoice.

        Args:
            invoice: The invoice data to validate.

        Returns:
            ValidationResult with errors and warnings.
        """
        result = ValidationResult()

        self._check_invoice_number_format(invoice, result)
        self._check_amount_range(invoice, result)
        self._check_po_number(invoice, result)
        self._check_approved_vendor(invoice, result)
        self._check_line_items_sum(invoice, result)
        self._check_date_sanity(invoice, result)

        if result.is_valid:
            logger.info(
                "Invoice %s passed all validation checks",
                invoice.invoice_number,
            )
        else:
            logger.warning(
                "Invoice %s failed validation: %s",
                invoice.invoice_number,
                "; ".join(result.errors),
            )

        return result

    def _check_invoice_number_format(
        self, invoice: InvoiceData, result: ValidationResult
    ) -> None:
        """Validate invoice number is non-empty and alphanumeric with dashes.

        Args:
            invoice: Invoice to check.
            result: Validation result to accumulate into.
        """
        if not invoice.invoice_number:
            result.add_error("Invoice number is empty")
            return

        # Allow alphanumeric, dashes, slashes, underscores
        import re

        if not re.match(r"^[A-Za-z0-9\-/_]+$", invoice.invoice_number):
            result.add_error(
                f"Invalid invoice number format: {invoice.invoice_number}"
            )

    def _check_amount_range(
        self, invoice: InvoiceData, result: ValidationResult
    ) -> None:
        """Validate total amount is within configured bounds.

        Args:
            invoice: Invoice to check.
            result: Validation result to accumulate into.
        """
        min_amount = Decimal(str(self._config.min_invoice_amount))
        max_amount = Decimal(str(self._config.max_invoice_amount))

        if invoice.total_amount < min_amount:
            result.add_error(
                f"Invoice amount {invoice.total_amount} is below "
                f"minimum {min_amount}"
            )
        elif invoice.total_amount > max_amount:
            result.add_error(
                f"Invoice amount {invoice.total_amount} exceeds "
                f"maximum {max_amount}"
            )

    def _check_po_number(
        self, invoice: InvoiceData, result: ValidationResult
    ) -> None:
        """Validate PO number exists and matches reference data.

        Args:
            invoice: Invoice to check.
            result: Validation result to accumulate into.
        """
        if invoice.po_number is None:
            result.add_warning("No PO number on invoice")
            return

        if self._valid_po_numbers and invoice.po_number not in self._valid_po_numbers:
            result.add_error(
                f"PO number {invoice.po_number} not found in reference data"
            )

    def _check_approved_vendor(
        self, invoice: InvoiceData, result: ValidationResult
    ) -> None:
        """Validate vendor is in the approved vendors list.

        Args:
            invoice: Invoice to check.
            result: Validation result to accumulate into.
        """
        if not self._approved_vendors:
            return  # Skip if no reference data loaded

        if invoice.vendor_name.strip().lower() not in self._approved_vendors:
            result.add_error(
                f"Vendor '{invoice.vendor_name}' is not an approved vendor"
            )

    def _check_line_items_sum(
        self, invoice: InvoiceData, result: ValidationResult
    ) -> None:
        """Validate that line item amounts sum to the total.

        Args:
            invoice: Invoice to check.
            result: Validation result to accumulate into.
        """
        if not invoice.line_items:
            result.add_warning("No line items found on invoice")
            return

        items_sum = sum(item.total for item in invoice.line_items)
        if items_sum != invoice.total_amount:
            result.add_error(
                f"Line items sum ({items_sum}) does not match "
                f"total amount ({invoice.total_amount})"
            )

    def _check_date_sanity(
        self, invoice: InvoiceData, result: ValidationResult
    ) -> None:
        """Validate invoice date is not in the future or too old.

        Args:
            invoice: Invoice to check.
            result: Validation result to accumulate into.
        """
        today = date.today()
        max_age = timedelta(days=self._config.max_invoice_age_days)

        if invoice.invoice_date > today:
            result.add_error(
                f"Invoice date {invoice.invoice_date} is in the future"
            )

        if invoice.invoice_date < today - max_age:
            result.add_error(
                f"Invoice date {invoice.invoice_date} is older than "
                f"{self._config.max_invoice_age_days} days"
            )

        if invoice.due_date is not None and invoice.due_date < invoice.invoice_date:
            result.add_warning("Due date is before invoice date")
