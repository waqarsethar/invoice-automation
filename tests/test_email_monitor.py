"""Tests for the email monitor component."""

import email.mime.application
import email.mime.multipart
import email.mime.text
from unittest.mock import MagicMock, patch

import pytest

from src.config_loader import EmailConfig
from src.email_monitor import EmailMonitor
from src.exceptions import EmailConnectionError


@pytest.fixture
def email_config() -> EmailConfig:
    """Test email configuration."""
    return EmailConfig(
        imap_host="imap.test.com",
        imap_port=993,
        address="test@test.com",
        password="test-pass",
        search_subject="Invoice",
        folder="INBOX",
    )


@pytest.fixture
def monitor(email_config: EmailConfig) -> EmailMonitor:
    """EmailMonitor instance for testing."""
    return EmailMonitor(email_config)


def _make_email_with_pdf(
    subject: str = "Invoice from Acme",
    sender: str = "billing@acme.com",
    filename: str = "invoice.pdf",
    pdf_content: bytes = b"%PDF-1.4 test",
) -> bytes:
    """Create a raw email with a PDF attachment."""
    msg = email.mime.multipart.MIMEMultipart()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["Date"] = "Mon, 15 Jan 2024 10:30:00 +0000"

    body = email.mime.text.MIMEText("Please see attached invoice.")
    msg.attach(body)

    attachment = email.mime.application.MIMEApplication(
        pdf_content, _subtype="pdf"
    )
    attachment.add_header(
        "Content-Disposition", "attachment", filename=filename
    )
    msg.attach(attachment)

    return msg.as_bytes()


class TestEmailMonitorConnect:
    """Tests for connection management."""

    @patch("src.email_monitor.imaplib.IMAP4_SSL")
    def test_connect_success(
        self, mock_imap_class: MagicMock, monitor: EmailMonitor
    ) -> None:
        """Successful connection sets up IMAP."""
        mock_conn = MagicMock()
        mock_imap_class.return_value = mock_conn

        monitor.connect()

        mock_imap_class.assert_called_once_with("imap.test.com", 993)
        mock_conn.login.assert_called_once_with("test@test.com", "test-pass")
        mock_conn.select.assert_called_once_with("INBOX")

    @patch("src.email_monitor.imaplib.IMAP4_SSL")
    def test_connect_failure_raises(
        self, mock_imap_class: MagicMock, monitor: EmailMonitor
    ) -> None:
        """Connection failure raises EmailConnectionError."""
        mock_imap_class.side_effect = OSError("Connection refused")

        with pytest.raises(EmailConnectionError, match="Failed to connect"):
            monitor.connect()

    @patch("src.email_monitor.imaplib.IMAP4_SSL")
    def test_context_manager(
        self, mock_imap_class: MagicMock, monitor: EmailMonitor
    ) -> None:
        """Context manager connects and disconnects."""
        mock_conn = MagicMock()
        mock_imap_class.return_value = mock_conn

        with monitor:
            pass

        mock_conn.close.assert_called_once()
        mock_conn.logout.assert_called_once()


class TestEmailMonitorFetch:
    """Tests for email fetching."""

    @patch("src.email_monitor.imaplib.IMAP4_SSL")
    def test_fetch_no_emails(
        self, mock_imap_class: MagicMock, monitor: EmailMonitor
    ) -> None:
        """Returns empty list when no matching emails."""
        mock_conn = MagicMock()
        mock_imap_class.return_value = mock_conn
        mock_conn.search.return_value = ("OK", [b""])

        monitor.connect()
        result = monitor.fetch_invoice_emails()

        assert result == []

    @patch("src.email_monitor.imaplib.IMAP4_SSL")
    def test_fetch_with_pdf_attachment(
        self, mock_imap_class: MagicMock, monitor: EmailMonitor
    ) -> None:
        """Extracts PDF attachments from matching emails."""
        mock_conn = MagicMock()
        mock_imap_class.return_value = mock_conn
        mock_conn.search.return_value = ("OK", [b"1"])

        raw_email = _make_email_with_pdf()
        mock_conn.fetch.return_value = ("OK", [(b"1", raw_email)])

        monitor.connect()
        attachments = monitor.fetch_invoice_emails()

        assert len(attachments) == 1
        assert attachments[0].filename == "invoice.pdf"
        assert attachments[0].email_subject == "Invoice from Acme"
        assert attachments[0].email_from == "billing@acme.com"
        assert attachments[0].content == b"%PDF-1.4 test"

    def test_fetch_without_connection_raises(
        self, monitor: EmailMonitor
    ) -> None:
        """Fetching without connection raises EmailConnectionError."""
        with pytest.raises(EmailConnectionError, match="Not connected"):
            monitor.fetch_invoice_emails()

    @patch("src.email_monitor.imaplib.IMAP4_SSL")
    def test_fetch_multiple_emails(
        self, mock_imap_class: MagicMock, monitor: EmailMonitor
    ) -> None:
        """Handles multiple matching emails."""
        mock_conn = MagicMock()
        mock_imap_class.return_value = mock_conn
        mock_conn.search.return_value = ("OK", [b"1 2"])

        raw_email_1 = _make_email_with_pdf(filename="inv1.pdf")
        raw_email_2 = _make_email_with_pdf(filename="inv2.pdf")

        mock_conn.fetch.side_effect = [
            ("OK", [(b"1", raw_email_1)]),
            ("OK", [(b"2", raw_email_2)]),
        ]

        monitor.connect()
        attachments = monitor.fetch_invoice_emails()

        assert len(attachments) == 2
        assert attachments[0].filename == "inv1.pdf"
        assert attachments[1].filename == "inv2.pdf"


class TestEmailMonitorMarkProcessed:
    """Tests for marking emails as processed."""

    @patch("src.email_monitor.imaplib.IMAP4_SSL")
    def test_mark_as_processed(
        self, mock_imap_class: MagicMock, monitor: EmailMonitor
    ) -> None:
        """Marks email UID with Seen flag."""
        mock_conn = MagicMock()
        mock_imap_class.return_value = mock_conn

        monitor.connect()
        monitor.mark_as_processed("12345")

        mock_conn.store.assert_called_once_with(b"12345", "+FLAGS", "\\Seen")

    def test_mark_without_connection_raises(
        self, monitor: EmailMonitor
    ) -> None:
        """Marking without connection raises EmailConnectionError."""
        with pytest.raises(EmailConnectionError, match="Not connected"):
            monitor.mark_as_processed("12345")
