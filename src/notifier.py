"""Slack notification sender using Block Kit and webhooks."""

import logging

import requests

from src.config_loader import SlackConfig
from src.exceptions import NotificationError
from src.models import InvoiceData, ProcessingResult

logger = logging.getLogger("invoice_automation.slack_notifier")


class SlackNotifier:
    """Sends formatted Slack notifications via incoming webhooks.

    Uses Slack Block Kit for rich message formatting.

    Args:
        config: Slack webhook configuration.
    """

    def __init__(self, config: SlackConfig) -> None:
        self._config = config
        self._session = requests.Session()

    def notify_success(self, invoice: InvoiceData) -> None:
        """Send a success notification for a processed invoice.

        Args:
            invoice: The successfully processed invoice data.

        Raises:
            NotificationError: If the webhook request fails.
        """
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "Invoice Processed Successfully",
                },
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Invoice:* {invoice.invoice_number}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Vendor:* {invoice.vendor_name}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Amount:* ${invoice.total_amount:,.2f} {invoice.currency}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*PO:* {invoice.po_number or 'N/A'}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Date:* {invoice.invoice_date}",
                    },
                ],
            },
        ]

        self._send_message(blocks)
        logger.info(
            "Sent success notification for invoice %s",
            invoice.invoice_number,
        )

    def notify_failure(
        self, filename: str, error_message: str, email_from: str = ""
    ) -> None:
        """Send a failure notification for a failed invoice.

        Args:
            filename: Name of the PDF file that failed.
            error_message: Description of the failure.
            email_from: Sender of the source email.

        Raises:
            NotificationError: If the webhook request fails.
        """
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "Invoice Processing Failed",
                },
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*File:* {filename}"},
                    {"type": "mrkdwn", "text": f"*From:* {email_from or 'Unknown'}"},
                    {"type": "mrkdwn", "text": f"*Error:* {error_message}"},
                ],
            },
        ]

        self._send_message(blocks)
        logger.info("Sent failure notification for %s", filename)

    def notify_summary(self, results: list[ProcessingResult]) -> None:
        """Send a pipeline run summary notification.

        Args:
            results: List of all processing results from the run.

        Raises:
            NotificationError: If the webhook request fails.
        """
        total = len(results)
        successful = sum(1 for r in results if r.is_success)
        failed = total - successful

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "Invoice Pipeline Run Summary",
                },
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Total:* {total}"},
                    {"type": "mrkdwn", "text": f"*Successful:* {successful}"},
                    {"type": "mrkdwn", "text": f"*Failed:* {failed}"},
                ],
            },
        ]

        if failed > 0:
            failed_items = [r for r in results if not r.is_success]
            failure_lines = []
            for r in failed_items[:5]:  # Show at most 5 failures
                failure_lines.append(
                    f"- `{r.attachment.filename}`: {r.error_message or 'Unknown error'}"
                )
            if len(failed_items) > 5:
                failure_lines.append(f"_...and {len(failed_items) - 5} more_")

            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "*Failures:*\n" + "\n".join(failure_lines),
                    },
                }
            )

        self._send_message(blocks)
        logger.info(
            "Sent summary notification: %d total, %d successful, %d failed",
            total,
            successful,
            failed,
        )

    def _send_message(self, blocks: list[dict]) -> None:
        """Send a Block Kit message to the Slack webhook.

        Args:
            blocks: Slack Block Kit block list.

        Raises:
            NotificationError: If sending fails or webhook returns error.
        """
        if not self._config.enabled:
            logger.debug("Slack notifications disabled; skipping")
            return

        if not self._config.webhook_url:
            logger.warning("No Slack webhook URL configured")
            return

        payload: dict = {"blocks": blocks}
        if self._config.channel:
            payload["channel"] = self._config.channel

        try:
            response = self._session.post(
                self._config.webhook_url,
                json=payload,
                timeout=10,
            )
            if response.status_code != 200:
                raise NotificationError(
                    message=(
                        f"Slack webhook returned {response.status_code}: "
                        f"{response.text}"
                    ),
                )
        except requests.RequestException as exc:
            raise NotificationError(
                message=f"Failed to send Slack notification: {exc}",
            ) from exc
