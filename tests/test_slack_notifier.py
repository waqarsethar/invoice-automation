"""Tests for the Slack notifier component."""

from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from src.config_loader import SlackConfig
from src.exceptions import NotificationError
from src.models import (
    EmailAttachment,
    InvoiceData,
    ProcessingResult,
    ProcessingStatus,
)
from src.notifier import SlackNotifier


@pytest.fixture
def slack_config() -> SlackConfig:
    """Test Slack configuration."""
    return SlackConfig(
        webhook_url="https://hooks.slack.com/services/TEST/WEBHOOK/URL",
        enabled=True,
    )


@pytest.fixture
def notifier(slack_config: SlackConfig) -> SlackNotifier:
    """SlackNotifier instance for testing."""
    return SlackNotifier(slack_config)


@pytest.fixture
def sample_invoice() -> InvoiceData:
    """Sample invoice for notification tests."""
    return InvoiceData(
        invoice_number="INV-2024-001",
        vendor_name="Acme Corp",
        invoice_date=date(2024, 1, 15),
        due_date=date(2024, 2, 15),
        total_amount=Decimal("500.00"),
        po_number="PO-2024-100",
    )


@pytest.fixture
def sample_results() -> list[ProcessingResult]:
    """Sample processing results for summary tests."""
    attachment_ok = EmailAttachment(
        filename="inv1.pdf",
        content=b"",
        email_subject="Invoice",
        email_from="a@b.com",
        email_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        email_uid="1",
    )
    attachment_fail = EmailAttachment(
        filename="inv2.pdf",
        content=b"",
        email_subject="Invoice",
        email_from="c@d.com",
        email_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        email_uid="2",
    )
    return [
        ProcessingResult(
            attachment=attachment_ok,
            status=ProcessingStatus.STORED,
        ),
        ProcessingResult(
            attachment=attachment_fail,
            status=ProcessingStatus.FAILED,
            error_message="Parse error",
        ),
    ]


class TestSlackNotifierSuccess:
    """Tests for success notifications."""

    @patch("src.notifier.requests.Session.post")
    def test_notify_success_sends_message(
        self,
        mock_post: MagicMock,
        notifier: SlackNotifier,
        sample_invoice: InvoiceData,
    ) -> None:
        """Success notification sends correct payload."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        notifier.notify_success(sample_invoice)

        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert "blocks" in payload
        assert any(
            "Successfully" in str(block) for block in payload["blocks"]
        )


class TestSlackNotifierFailure:
    """Tests for failure notifications."""

    @patch("src.notifier.requests.Session.post")
    def test_notify_failure_sends_message(
        self,
        mock_post: MagicMock,
        notifier: SlackNotifier,
    ) -> None:
        """Failure notification sends correct payload."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        notifier.notify_failure("test.pdf", "Parse error", "sender@test.com")

        mock_post.assert_called_once()


class TestSlackNotifierSummary:
    """Tests for summary notifications."""

    @patch("src.notifier.requests.Session.post")
    def test_notify_summary_sends_message(
        self,
        mock_post: MagicMock,
        notifier: SlackNotifier,
        sample_results: list[ProcessingResult],
    ) -> None:
        """Summary notification includes counts."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        notifier.notify_summary(sample_results)

        mock_post.assert_called_once()
        payload = mock_post.call_args.kwargs.get("json") or mock_post.call_args[1].get("json")
        payload_str = str(payload)
        assert "2" in payload_str  # total
        assert "1" in payload_str  # successful and failed


class TestSlackNotifierErrors:
    """Tests for error handling."""

    @patch("src.notifier.requests.Session.post")
    def test_webhook_error_raises(
        self,
        mock_post: MagicMock,
        notifier: SlackNotifier,
        sample_invoice: InvoiceData,
    ) -> None:
        """Non-200 response raises NotificationError."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_post.return_value = mock_response

        with pytest.raises(NotificationError, match="500"):
            notifier.notify_success(sample_invoice)

    @patch("src.notifier.requests.Session.post")
    def test_request_exception_raises(
        self,
        mock_post: MagicMock,
        notifier: SlackNotifier,
        sample_invoice: InvoiceData,
    ) -> None:
        """Request exception raises NotificationError."""
        import requests

        mock_post.side_effect = requests.ConnectionError("Timeout")

        with pytest.raises(NotificationError, match="Failed to send"):
            notifier.notify_success(sample_invoice)

    def test_disabled_notifier_skips(
        self, sample_invoice: InvoiceData
    ) -> None:
        """Disabled notifier does not send."""
        config = SlackConfig(
            webhook_url="https://hooks.slack.com/test",
            enabled=False,
        )
        notifier = SlackNotifier(config)

        # Should not raise
        notifier.notify_success(sample_invoice)
