"""Email monitor for fetching invoice PDF attachments via IMAP."""

import email
import imaplib
import logging
from datetime import datetime, timezone
from email.message import Message
from typing import Self

from src.config_loader import EmailConfig
from src.exceptions import EmailConnectionError
from src.models import EmailAttachment

logger = logging.getLogger("invoice_automation.email_monitor")


class EmailMonitor:
    """Monitors an email inbox for invoice attachments via IMAP SSL.

    Use as a context manager to ensure the IMAP connection is properly
    closed after use.

    Args:
        config: Email server configuration.
    """

    def __init__(self, config: EmailConfig) -> None:
        self._config = config
        self._connection: imaplib.IMAP4_SSL | None = None

    def __enter__(self) -> Self:
        """Open IMAP connection and authenticate."""
        self.connect()
        return self

    def __exit__(self, exc_type: type | None, exc_val: Exception | None, exc_tb: object) -> bool:
        """Close IMAP connection."""
        self.disconnect()
        return False

    def connect(self) -> None:
        """Establish IMAP SSL connection and log in.

        Raises:
            EmailConnectionError: If connection or authentication fails.
        """
        try:
            logger.info(
                "Connecting to IMAP server %s:%d",
                self._config.imap_host,
                self._config.imap_port,
            )
            self._connection = imaplib.IMAP4_SSL(
                self._config.imap_host,
                self._config.imap_port,
            )
            self._connection.login(
                self._config.address,
                self._config.password,
            )
            self._connection.select(self._config.folder)
            logger.info("Successfully connected to email server")
        except (imaplib.IMAP4.error, OSError) as exc:
            raise EmailConnectionError(
                message=f"Failed to connect to email server: {exc}",
                details={"host": self._config.imap_host},
            ) from exc

    def disconnect(self) -> None:
        """Close IMAP connection gracefully."""
        if self._connection is not None:
            try:
                self._connection.close()
                self._connection.logout()
            except Exception:
                logger.warning("Error during IMAP disconnect", exc_info=True)
            finally:
                self._connection = None

    def fetch_invoice_emails(self) -> list[EmailAttachment]:
        """Fetch unseen emails matching the invoice subject filter.

        Searches for UNSEEN emails with subject containing the configured
        search string, then extracts all PDF attachments.

        Returns:
            List of EmailAttachment objects containing PDF data.

        Raises:
            EmailConnectionError: If not connected or fetch fails.
        """
        if self._connection is None:
            raise EmailConnectionError(
                message="Not connected to email server"
            )

        try:
            search_criteria = f'(UNSEEN SUBJECT "{self._config.search_subject}")'
            logger.info("Searching for emails with criteria: %s", search_criteria)

            status, message_ids = self._connection.search(None, search_criteria)
            if status != "OK" or not message_ids[0]:
                logger.info("No matching emails found")
                return []

            uid_list = message_ids[0].split()
            logger.info("Found %d matching email(s)", len(uid_list))

            attachments: list[EmailAttachment] = []
            for uid in uid_list:
                uid_str = uid.decode("utf-8")
                email_attachments = self._extract_attachments(uid_str)
                attachments.extend(email_attachments)

            logger.info(
                "Extracted %d PDF attachment(s) total", len(attachments)
            )
            return attachments

        except imaplib.IMAP4.error as exc:
            raise EmailConnectionError(
                message=f"Failed to fetch emails: {exc}",
            ) from exc

    def _extract_attachments(self, uid: str) -> list[EmailAttachment]:
        """Extract PDF attachments from a single email.

        Args:
            uid: IMAP UID of the email message.

        Returns:
            List of EmailAttachment objects for PDF files found.
        """
        assert self._connection is not None

        status, msg_data = self._connection.fetch(uid.encode(), "(RFC822)")
        if status != "OK" or msg_data[0] is None:
            logger.warning("Failed to fetch email UID %s", uid)
            return []

        raw_email = msg_data[0][1]
        msg: Message = email.message_from_bytes(raw_email)

        email_subject = msg.get("Subject", "")
        email_from = msg.get("From", "")
        email_date_str = msg.get("Date", "")

        try:
            email_date = email.utils.parsedate_to_datetime(email_date_str)
        except (ValueError, TypeError):
            email_date = datetime.now(timezone.utc)

        attachments: list[EmailAttachment] = []
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition", ""))

            if "attachment" not in content_disposition:
                continue

            filename = part.get_filename()
            if filename is None or not filename.lower().endswith(".pdf"):
                continue

            payload = part.get_payload(decode=True)
            if payload is None:
                continue

            attachment = EmailAttachment(
                filename=filename,
                content=payload,
                email_subject=email_subject,
                email_from=email_from,
                email_date=email_date,
                email_uid=uid,
            )
            attachments.append(attachment)
            logger.debug(
                "Found PDF attachment: %s (UID: %s)", filename, uid
            )

        return attachments

    def mark_as_processed(self, uid: str) -> None:
        """Mark an email as processed by adding a SEEN flag.

        Args:
            uid: IMAP UID of the email to mark.

        Raises:
            EmailConnectionError: If not connected or flag operation fails.
        """
        if self._connection is None:
            raise EmailConnectionError(
                message="Not connected to email server"
            )

        try:
            self._connection.store(uid.encode(), "+FLAGS", "\\Seen")
            logger.debug("Marked email UID %s as processed", uid)
        except imaplib.IMAP4.error as exc:
            raise EmailConnectionError(
                message=f"Failed to mark email as processed: {exc}",
                details={"uid": uid},
            ) from exc
