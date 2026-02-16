"""Tests for the PDF parser component."""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from src.exceptions import PDFExtractionError
from src.pdf_parser import PDFParser

SAMPLE_INVOICE_TEXT = """
INVOICE

Invoice Number: INV-2024-001
Date: 01/15/2024
Due Date: 02/15/2024

Vendor: Acme Corp
PO Number: PO-2024-100

Description          Qty    Unit Price    Amount
Widget A              10       25.00    250.00
Widget B               5       50.00    250.00

                              Total:    $500.00
"""


@pytest.fixture
def parser() -> PDFParser:
    """PDFParser instance for testing."""
    return PDFParser()


class TestPDFParserExtraction:
    """Tests for PDF text extraction and parsing."""

    @patch("src.pdf_parser.pdfplumber.open")
    def test_parse_valid_invoice(
        self, mock_open: MagicMock, parser: PDFParser
    ) -> None:
        """Parses a well-formatted invoice correctly."""
        mock_page = MagicMock()
        mock_page.extract_text.return_value = SAMPLE_INVOICE_TEXT
        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
        mock_pdf.__exit__ = MagicMock(return_value=False)
        mock_open.return_value = mock_pdf

        result = parser.parse(b"fake-pdf", "test.pdf")

        assert result.invoice_number == "INV-2024-001"
        assert result.vendor_name == "Acme Corp"
        assert result.total_amount == Decimal("500.00")
        assert result.po_number == "PO-2024-100"
        assert result.invoice_date.year == 2024
        assert result.invoice_date.month == 1
        assert result.invoice_date.day == 15

    @patch("src.pdf_parser.pdfplumber.open")
    def test_parse_empty_pdf_raises(
        self, mock_open: MagicMock, parser: PDFParser
    ) -> None:
        """Empty PDF raises PDFExtractionError."""
        mock_page = MagicMock()
        mock_page.extract_text.return_value = ""
        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
        mock_pdf.__exit__ = MagicMock(return_value=False)
        mock_open.return_value = mock_pdf

        with pytest.raises(PDFExtractionError, match="No text extracted"):
            parser.parse(b"fake-pdf", "empty.pdf")

    @patch("src.pdf_parser.pdfplumber.open")
    def test_parse_missing_invoice_number_raises(
        self, mock_open: MagicMock, parser: PDFParser
    ) -> None:
        """Missing invoice number raises PDFExtractionError."""
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Vendor: Acme Corp\nTotal: $500.00"
        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
        mock_pdf.__exit__ = MagicMock(return_value=False)
        mock_open.return_value = mock_pdf

        with pytest.raises(PDFExtractionError, match="invoice number"):
            parser.parse(b"fake-pdf", "no_inv_num.pdf")

    @patch("src.pdf_parser.pdfplumber.open")
    def test_parse_missing_vendor_raises(
        self, mock_open: MagicMock, parser: PDFParser
    ) -> None:
        """Missing vendor name raises PDFExtractionError."""
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Invoice Number: INV-001\nTotal: $500.00"
        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
        mock_pdf.__exit__ = MagicMock(return_value=False)
        mock_open.return_value = mock_pdf

        with pytest.raises(PDFExtractionError, match="vendor name"):
            parser.parse(b"fake-pdf", "no_vendor.pdf")

    @patch("src.pdf_parser.pdfplumber.open")
    def test_parse_missing_total_raises(
        self, mock_open: MagicMock, parser: PDFParser
    ) -> None:
        """Missing total amount raises PDFExtractionError."""
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Invoice Number: INV-001\nVendor: Acme"
        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
        mock_pdf.__exit__ = MagicMock(return_value=False)
        mock_open.return_value = mock_pdf

        with pytest.raises(PDFExtractionError, match="total amount"):
            parser.parse(b"fake-pdf", "no_total.pdf")

    @patch("src.pdf_parser.pdfplumber.open")
    def test_parse_corrupted_pdf_raises(
        self, mock_open: MagicMock, parser: PDFParser
    ) -> None:
        """Corrupted PDF raises PDFExtractionError."""
        mock_open.side_effect = Exception("Bad PDF")

        with pytest.raises(PDFExtractionError, match="Failed to extract"):
            parser.parse(b"corrupted", "bad.pdf")

    @patch("src.pdf_parser.pdfplumber.open")
    def test_parse_line_items(
        self, mock_open: MagicMock, parser: PDFParser
    ) -> None:
        """Extracts line items from invoice text."""
        mock_page = MagicMock()
        mock_page.extract_text.return_value = SAMPLE_INVOICE_TEXT
        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
        mock_pdf.__exit__ = MagicMock(return_value=False)
        mock_open.return_value = mock_pdf

        result = parser.parse(b"fake-pdf", "test.pdf")

        assert len(result.line_items) == 2
        assert result.line_items[0].description == "Widget A"
        assert result.line_items[0].quantity == 10
        assert result.line_items[0].unit_price == Decimal("25.00")
        assert result.line_items[0].total == Decimal("250.00")

    @patch("src.pdf_parser.pdfplumber.open")
    def test_parse_due_date(
        self, mock_open: MagicMock, parser: PDFParser
    ) -> None:
        """Extracts due date when present."""
        mock_page = MagicMock()
        mock_page.extract_text.return_value = SAMPLE_INVOICE_TEXT
        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
        mock_pdf.__exit__ = MagicMock(return_value=False)
        mock_open.return_value = mock_pdf

        result = parser.parse(b"fake-pdf", "test.pdf")

        assert result.due_date is not None
        assert result.due_date.month == 2
        assert result.due_date.day == 15
