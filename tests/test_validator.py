"""Tests for the invoice validator component."""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from src.config_loader import ValidationConfig
from src.models import InvoiceData, LineItem, ValidationResult
from src.validator import InvoiceValidator


@pytest.fixture
def validator(tmp_path) -> InvoiceValidator:
    """InvoiceValidator with sample reference data."""
    # Create PO numbers CSV
    po_file = tmp_path / "po_numbers.csv"
    po_file.write_text("po_number\nPO-2024-100\nPO-2024-200\nPO-2024-300\n")

    # Create approved vendors CSV
    vendors_file = tmp_path / "approved_vendors.csv"
    vendors_file.write_text("vendor_name\nAcme Corp\nGlobal Supplies\nTech Parts Inc\n")

    config = ValidationConfig(
        max_invoice_amount=1_000_000.00,
        min_invoice_amount=0.01,
        po_numbers_file=str(po_file),
        approved_vendors_file=str(vendors_file),
        max_invoice_age_days=365,
    )
    return InvoiceValidator(config)


@pytest.fixture
def valid_invoice() -> InvoiceData:
    """An invoice that passes all validation checks."""
    return InvoiceData(
        invoice_number="INV-2024-001",
        vendor_name="Acme Corp",
        invoice_date=date.today() - timedelta(days=10),
        due_date=date.today() + timedelta(days=20),
        total_amount=Decimal("500.00"),
        po_number="PO-2024-100",
        line_items=[
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
        ],
    )


class TestInvoiceValidator:
    """Tests for validation rules."""

    def test_valid_invoice_passes(
        self, validator: InvoiceValidator, valid_invoice: InvoiceData
    ) -> None:
        """A valid invoice passes all checks."""
        result = validator.validate(valid_invoice)
        assert result.is_valid
        assert len(result.errors) == 0

    def test_empty_invoice_number_fails(
        self, validator: InvoiceValidator, valid_invoice: InvoiceData
    ) -> None:
        """Empty invoice number fails format check."""
        valid_invoice.invoice_number = ""
        result = validator.validate(valid_invoice)
        assert not result.is_valid
        assert any("empty" in e.lower() for e in result.errors)

    def test_invalid_invoice_number_format(
        self, validator: InvoiceValidator, valid_invoice: InvoiceData
    ) -> None:
        """Special characters in invoice number fail format check."""
        valid_invoice.invoice_number = "INV@#$"
        result = validator.validate(valid_invoice)
        assert not result.is_valid
        assert any("format" in e.lower() for e in result.errors)

    def test_amount_below_minimum_fails(
        self, validator: InvoiceValidator, valid_invoice: InvoiceData
    ) -> None:
        """Amount below minimum fails range check."""
        valid_invoice.total_amount = Decimal("0.00")
        result = validator.validate(valid_invoice)
        assert not result.is_valid
        assert any("below" in e.lower() for e in result.errors)

    def test_amount_above_maximum_fails(
        self, validator: InvoiceValidator, valid_invoice: InvoiceData
    ) -> None:
        """Amount above maximum fails range check."""
        valid_invoice.total_amount = Decimal("2000000.00")
        result = validator.validate(valid_invoice)
        assert not result.is_valid
        assert any("exceeds" in e.lower() for e in result.errors)

    def test_unknown_po_number_fails(
        self, validator: InvoiceValidator, valid_invoice: InvoiceData
    ) -> None:
        """PO number not in reference data fails."""
        valid_invoice.po_number = "PO-UNKNOWN"
        result = validator.validate(valid_invoice)
        assert not result.is_valid
        assert any("not found" in e.lower() for e in result.errors)

    def test_missing_po_number_warns(
        self, validator: InvoiceValidator, valid_invoice: InvoiceData
    ) -> None:
        """Missing PO number produces warning, not error."""
        valid_invoice.po_number = None
        result = validator.validate(valid_invoice)
        # Missing PO is a warning, not an error
        assert any("no po" in w.lower() for w in result.warnings)

    def test_unapproved_vendor_fails(
        self, validator: InvoiceValidator, valid_invoice: InvoiceData
    ) -> None:
        """Vendor not in approved list fails."""
        valid_invoice.vendor_name = "Unknown Vendor LLC"
        result = validator.validate(valid_invoice)
        assert not result.is_valid
        assert any("not an approved vendor" in e.lower() for e in result.errors)

    def test_line_items_sum_mismatch_fails(
        self, validator: InvoiceValidator, valid_invoice: InvoiceData
    ) -> None:
        """Line items that don't sum to total fail."""
        valid_invoice.total_amount = Decimal("999.99")
        result = validator.validate(valid_invoice)
        assert not result.is_valid
        assert any("does not match" in e.lower() for e in result.errors)

    def test_no_line_items_warns(
        self, validator: InvoiceValidator, valid_invoice: InvoiceData
    ) -> None:
        """Missing line items produces warning."""
        valid_invoice.line_items = []
        result = validator.validate(valid_invoice)
        assert any("no line items" in w.lower() for w in result.warnings)

    def test_future_date_fails(
        self, validator: InvoiceValidator, valid_invoice: InvoiceData
    ) -> None:
        """Invoice date in the future fails."""
        valid_invoice.invoice_date = date.today() + timedelta(days=30)
        result = validator.validate(valid_invoice)
        assert not result.is_valid
        assert any("future" in e.lower() for e in result.errors)

    def test_very_old_date_fails(
        self, validator: InvoiceValidator, valid_invoice: InvoiceData
    ) -> None:
        """Invoice date older than max age fails."""
        valid_invoice.invoice_date = date.today() - timedelta(days=400)
        result = validator.validate(valid_invoice)
        assert not result.is_valid
        assert any("older" in e.lower() for e in result.errors)

    def test_due_date_before_invoice_date_warns(
        self, validator: InvoiceValidator, valid_invoice: InvoiceData
    ) -> None:
        """Due date before invoice date produces warning."""
        valid_invoice.due_date = valid_invoice.invoice_date - timedelta(days=5)
        result = validator.validate(valid_invoice)
        assert any("before invoice date" in w.lower() for w in result.warnings)


class TestValidationResult:
    """Tests for the ValidationResult dataclass."""

    def test_add_error_invalidates(self) -> None:
        """Adding an error sets is_valid to False."""
        result = ValidationResult()
        assert result.is_valid
        result.add_error("Test error")
        assert not result.is_valid
        assert result.errors == ["Test error"]

    def test_add_warning_keeps_valid(self) -> None:
        """Adding a warning keeps is_valid True."""
        result = ValidationResult()
        result.add_warning("Test warning")
        assert result.is_valid
        assert result.warnings == ["Test warning"]
