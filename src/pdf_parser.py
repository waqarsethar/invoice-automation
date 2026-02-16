"""PDF text extraction and invoice data parsing."""

import logging
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO

import pdfplumber

from src.exceptions import PDFExtractionError
from src.models import InvoiceData, LineItem

logger = logging.getLogger("invoice_automation.pdf_parser")

# Regex patterns for invoice field extraction
INVOICE_NUMBER_PATTERNS = [
    re.compile(r"Invoice\s*(?:Number|No\.?|#)\s*:?\s*([A-Z0-9][\w-]+)", re.IGNORECASE),
    re.compile(r"(INV[-/]\d{4}[-/]\d{3,6})", re.IGNORECASE),
]

DATE_PATTERNS = [
    re.compile(r"(?:Invoice\s+)?Date\s*:?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})", re.IGNORECASE),
    re.compile(r"Date\s*:?\s*(\w+\s+\d{1,2},?\s+\d{4})", re.IGNORECASE),
]

DUE_DATE_PATTERNS = [
    re.compile(r"Due\s*Date\s*:?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})", re.IGNORECASE),
    re.compile(r"Due\s*Date\s*:?\s*(\w+\s+\d{1,2},?\s+\d{4})", re.IGNORECASE),
]

TOTAL_PATTERNS = [
    re.compile(r"Total\s*:?\s*\$?([\d,]+\.\d{2})", re.IGNORECASE),
    re.compile(r"Amount\s+Due\s*:?\s*\$?([\d,]+\.\d{2})", re.IGNORECASE),
    re.compile(r"Grand\s+Total\s*:?\s*\$?([\d,]+\.\d{2})", re.IGNORECASE),
]

VENDOR_PATTERNS = [
    re.compile(r"Vendor\s*:?\s*(.+?)(?:\n|$)", re.IGNORECASE),
    re.compile(r"(?:From|Supplier|Company)\s*:?\s*(.+?)(?:\n|$)", re.IGNORECASE),
    re.compile(r"Bill\s+From\s*:?\s*(.+?)(?:\n|$)", re.IGNORECASE),
]

PO_NUMBER_PATTERNS = [
    re.compile(r"(?:PO|Purchase\s+Order)\s*(?:Number|No\.?|#)?\s*:?\s*([A-Z0-9][\w-]+)", re.IGNORECASE),
]

LINE_ITEM_PATTERN = re.compile(
    r"^(.+?)\s+(\d+)\s+\$?([\d,]+\.\d{2})\s+\$?([\d,]+\.\d{2})\s*$",
    re.MULTILINE,
)


class PDFParser:
    """Extracts structured invoice data from PDF content.

    Uses pdfplumber for text extraction and regex patterns for
    field-level parsing.
    """

    def parse(self, pdf_content: bytes, filename: str = "") -> InvoiceData:
        """Extract invoice data from PDF bytes.

        Args:
            pdf_content: Raw bytes of the PDF file.
            filename: Original filename for logging context.

        Returns:
            Parsed InvoiceData with extracted fields.

        Raises:
            PDFExtractionError: If PDF cannot be read or critical fields
                are missing.
        """
        logger.info("Parsing PDF: %s", filename or "<bytes>")
        text = self._extract_text(pdf_content, filename)

        if not text.strip():
            raise PDFExtractionError(
                message=f"No text extracted from PDF: {filename}",
                details={"filename": filename},
            )

        logger.debug("Extracted text length: %d characters", len(text))

        invoice_number = self._extract_field(
            text, INVOICE_NUMBER_PATTERNS, "invoice_number"
        )
        if invoice_number is None:
            raise PDFExtractionError(
                message=f"Could not extract invoice number from: {filename}",
                details={"filename": filename},
            )

        vendor_name = self._extract_field(
            text, VENDOR_PATTERNS, "vendor_name"
        )
        if vendor_name is None:
            raise PDFExtractionError(
                message=f"Could not extract vendor name from: {filename}",
                details={"filename": filename},
            )

        total_str = self._extract_field(text, TOTAL_PATTERNS, "total_amount")
        if total_str is None:
            raise PDFExtractionError(
                message=f"Could not extract total amount from: {filename}",
                details={"filename": filename},
            )

        total_amount = self._parse_amount(total_str)
        invoice_date = self._extract_date(text, DATE_PATTERNS, "invoice_date")
        due_date = self._extract_date(text, DUE_DATE_PATTERNS, "due_date")
        po_number = self._extract_field(text, PO_NUMBER_PATTERNS, "po_number")
        line_items = self._extract_line_items(text)

        invoice = InvoiceData(
            invoice_number=invoice_number.strip(),
            vendor_name=vendor_name.strip(),
            invoice_date=invoice_date or date.today(),
            due_date=due_date,
            total_amount=total_amount,
            po_number=po_number.strip() if po_number else None,
            line_items=line_items,
            raw_text=text,
        )

        logger.info(
            "Successfully parsed invoice %s from %s (total: %s)",
            invoice.invoice_number,
            invoice.vendor_name,
            invoice.total_amount,
        )
        return invoice

    def _extract_text(self, pdf_content: bytes, filename: str) -> str:
        """Extract all text from a PDF.

        Args:
            pdf_content: Raw PDF bytes.
            filename: Filename for error context.

        Returns:
            Concatenated text from all pages.

        Raises:
            PDFExtractionError: If PDF cannot be opened or read.
        """
        try:
            with pdfplumber.open(BytesIO(pdf_content)) as pdf:
                pages_text: list[str] = []
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        pages_text.append(page_text)
                return "\n".join(pages_text)
        except Exception as exc:
            raise PDFExtractionError(
                message=f"Failed to extract text from PDF: {filename}: {exc}",
                details={"filename": filename},
            ) from exc

    def _extract_field(
        self,
        text: str,
        patterns: list[re.Pattern[str]],
        field_name: str,
    ) -> str | None:
        """Try multiple regex patterns to extract a field value.

        Args:
            text: Full text to search.
            patterns: Ordered list of regex patterns to try.
            field_name: Name of the field (for logging).

        Returns:
            First matched group, or None if no pattern matches.
        """
        for pattern in patterns:
            match = pattern.search(text)
            if match:
                value = match.group(1).strip()
                logger.debug("Extracted %s: %s", field_name, value)
                return value
        logger.debug("Could not extract %s", field_name)
        return None

    def _extract_date(
        self,
        text: str,
        patterns: list[re.Pattern[str]],
        field_name: str,
    ) -> date | None:
        """Extract and parse a date field from text.

        Args:
            text: Full text to search.
            patterns: Ordered list of regex patterns to try.
            field_name: Name of the field (for logging).

        Returns:
            Parsed date, or None if not found or unparseable.
        """
        date_str = self._extract_field(text, patterns, field_name)
        if date_str is None:
            return None
        return self._parse_date(date_str)

    def _parse_date(self, date_str: str) -> date | None:
        """Parse a date string in common formats.

        Args:
            date_str: Date string to parse.

        Returns:
            Parsed date, or None if format is unrecognized.
        """
        formats = [
            "%m/%d/%Y",
            "%m-%d-%Y",
            "%d/%m/%Y",
            "%d-%m-%Y",
            "%m/%d/%y",
            "%m-%d-%y",
            "%B %d, %Y",
            "%b %d, %Y",
            "%B %d %Y",
            "%b %d %Y",
        ]
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt).date()
            except ValueError:
                continue
        logger.warning("Could not parse date: %s", date_str)
        return None

    def _parse_amount(self, amount_str: str) -> Decimal:
        """Parse a monetary amount string to Decimal.

        Args:
            amount_str: Amount string, possibly with commas.

        Returns:
            Parsed Decimal amount.

        Raises:
            PDFExtractionError: If amount cannot be parsed.
        """
        try:
            cleaned = amount_str.replace(",", "").replace("$", "").strip()
            return Decimal(cleaned)
        except InvalidOperation as exc:
            raise PDFExtractionError(
                message=f"Invalid amount format: {amount_str}",
                details={"raw_amount": amount_str},
            ) from exc

    def _extract_line_items(self, text: str) -> list[LineItem]:
        """Extract line items from invoice text.

        Args:
            text: Full invoice text.

        Returns:
            List of parsed LineItem objects.
        """
        items: list[LineItem] = []
        for match in LINE_ITEM_PATTERN.finditer(text):
            try:
                description = match.group(1).strip()
                quantity = int(match.group(2))
                unit_price = Decimal(match.group(3).replace(",", ""))
                total = Decimal(match.group(4).replace(",", ""))

                items.append(
                    LineItem(
                        description=description,
                        quantity=quantity,
                        unit_price=unit_price,
                        total=total,
                    )
                )
            except (ValueError, InvalidOperation):
                logger.warning(
                    "Skipping unparseable line item: %s", match.group(0)
                )

        logger.debug("Extracted %d line item(s)", len(items))
        return items
