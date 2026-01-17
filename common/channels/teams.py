"""Microsoft Teams webhook channel (Workflows / Power Automate version).

Send messages to Teams channels via the new Workflows webhook.
This replaces the deprecated Incoming Webhook connector.

Setup:
1. In Teams channel, click ... > Workflows
2. Search "Post to a channel when a webhook request is received"
3. Select team/channel and create
4. Copy the webhook URL
"""

import json
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class TeamsMessage:
    """Teams message content using Adaptive Card format."""
    title: str
    facts: list[tuple[str, str]] = field(default_factory=list)
    text: str | None = None
    color: str = "Attention"  # Good, Attention, Warning, Accent, Default


class TeamsWebhookChannel:
    """Send messages to Microsoft Teams via Workflows webhook."""

    def __init__(self, webhook_url: str):
        """
        Initialize Teams webhook channel.

        Args:
            webhook_url: The Workflows webhook URL from Teams
        """
        self.webhook_url = webhook_url

    def _build_adaptive_card(
        self,
        title: str,
        facts: list[tuple[str, str]],
        text: str | None = None,
        color: str = "Attention",
    ) -> dict:
        """Build an Adaptive Card payload for Teams Workflows."""
        body = [
            {
                "type": "TextBlock",
                "text": title,
                "weight": "Bolder",
                "size": "Large",
                "color": color,
                "wrap": True,
            }
        ]

        if facts:
            body.append({
                "type": "FactSet",
                "facts": [{"title": k, "value": v} for k, v in facts],
            })

        if text:
            body.append({
                "type": "Container",
                "style": "warning" if color == "Attention" else "default",
                "items": [
                    {
                        "type": "TextBlock",
                        "text": text,
                        "wrap": True,
                    }
                ],
            })

        body.append({
            "type": "TextBlock",
            "text": f"Sent: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "size": "Small",
            "isSubtle": True,
            "wrap": True,
        })

        return {
            "type": "AdaptiveCard",
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "version": "1.4",
            "body": body,
        }

    def _build_wrapped_payload(self, card: dict) -> dict:
        """Wrap Adaptive Card in message/attachments format for Workflows."""
        return {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "contentUrl": None,
                    "content": card,
                }
            ],
        }

    def _send_request(self, payload: dict) -> tuple[bool, int, str]:
        """Send HTTP request and return (success, status_code, response_text)."""
        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                self.webhook_url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )

            with urllib.request.urlopen(req, timeout=30) as response:
                return True, response.status, response.read().decode("utf-8", errors="ignore")

        except urllib.error.HTTPError as e:
            return False, e.code, e.read().decode("utf-8", errors="ignore")[:200]
        except urllib.error.URLError as e:
            return False, 0, str(e.reason)
        except Exception as e:
            return False, 0, str(e)

    def send(self, message: TeamsMessage) -> bool:
        """
        Send a message to Teams.

        Args:
            message: The message to send

        Returns:
            True if sent successfully, False otherwise
        """
        if not self.webhook_url:
            print("  Teams: No webhook URL configured")
            return False

        card = self._build_adaptive_card(
            title=message.title,
            facts=message.facts,
            text=message.text,
            color=message.color,
        )

        # Try wrapped format first (works with most Workflows setups)
        payload = self._build_wrapped_payload(card)
        success, status, response_text = self._send_request(payload)

        if success and status in (200, 202):
            print("  Teams message sent")
            return True

        # Try unwrapped Adaptive Card format as fallback
        print(f"  Teams: Wrapped format failed ({status}), trying direct card...")
        success, status, response_text = self._send_request(card)

        if success and status in (200, 202):
            print("  Teams message sent (direct card)")
            return True

        print(f"  Teams failed: {status} - {response_text}")
        return False

    def send_simple(
        self,
        title: str,
        text: str,
        color: str = "Attention",
    ) -> bool:
        """
        Send a simple message to Teams.

        Args:
            title: Message title
            text: Message body
            color: Card color (Good, Attention, Warning, Accent, Default)

        Returns:
            True if sent successfully, False otherwise
        """
        return self.send(TeamsMessage(
            title=title,
            text=text,
            color=color,
        ))

    def send_card(
        self,
        title: str,
        facts: list[tuple[str, str]],
        text: str | None = None,
        color: str = "Attention",
        theme_color: str | None = None,  # Ignored, kept for backwards compatibility
    ) -> bool:
        """
        Send a card with key-value facts to Teams.

        Args:
            title: Card title
            facts: List of (name, value) tuples
            text: Optional additional text
            color: Card color (Good, Attention, Warning, Accent, Default)
            theme_color: Deprecated, ignored (was for old MessageCard format)

        Returns:
            True if sent successfully, False otherwise
        """
        return self.send(TeamsMessage(
            title=title,
            facts=facts,
            text=text,
            color=color,
        ))

    def is_configured(self) -> bool:
        """Check if channel is configured."""
        return bool(self.webhook_url)


def test_webhook(webhook_url: str) -> bool:
    """
    Send a test message to verify webhook configuration.

    Usage:
        python -c "from common.channels.teams import test_webhook; test_webhook('YOUR_URL')"
    """
    channel = TeamsWebhookChannel(webhook_url)

    print("Sending test to Workflows webhook...")

    success = channel.send(TeamsMessage(
        title="✅ ASP Alerts - Test Message",
        facts=[
            ("Status", "Webhook configured correctly"),
            ("Time", datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
        ],
        text="If you see this in Teams, your webhook is working!",
        color="Good",
    ))

    if success:
        print("✅ SUCCESS! Check your Teams channel for the test message.")
    else:
        print("❌ FAILED - see error above")

    return success
