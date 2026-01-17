#!/usr/bin/env python3
"""Test script for Microsoft Teams Workflows webhook.

Usage:
    python test_teams_webhook.py "https://prod-XX.westus.logic.azure.com:443/workflows/..."

Or set environment variable:
    export TEAMS_WEBHOOK_URL="https://prod-XX.westus.logic.azure.com:443/workflows/..."
    python test_teams_webhook.py
"""

import os
import sys
from datetime import datetime

import requests


def test_webhook(webhook_url: str) -> bool:
    """Send a test alert card to verify webhook configuration."""

    # Build test Adaptive Card that mimics a real alert
    test_card = {
        "type": "AdaptiveCard",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "version": "1.4",
        "body": [
            {
                "type": "TextBlock",
                "text": "✅ ASP Bacteremia Alerts - Test Message",
                "weight": "Bolder",
                "size": "Large",
                "color": "Good",
                "wrap": True
            },
            {
                "type": "FactSet",
                "facts": [
                    {"title": "Patient", "value": "Test Patient (TEST000)"},
                    {"title": "Location", "value": "Test Unit - Room 101"},
                    {"title": "Organism", "value": "Staphylococcus aureus (TEST)"},
                    {"title": "Gram Stain", "value": "Gram positive cocci in clusters"},
                    {"title": "Current Abx", "value": "None"},
                    {"title": "Status", "value": "⚠️ INADEQUATE (TEST)"}
                ]
            },
            {
                "type": "Container",
                "style": "warning",
                "items": [
                    {
                        "type": "TextBlock",
                        "text": "**Recommendation**",
                        "wrap": True
                    },
                    {
                        "type": "TextBlock",
                        "text": "This is a TEST alert. Consider empiric coverage with vancomycin pending susceptibilities.",
                        "wrap": True
                    }
                ]
            },
            {
                "type": "TextBlock",
                "text": f"Test sent: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                "size": "Small",
                "isSubtle": True,
                "wrap": True
            },
            {
                "type": "TextBlock",
                "text": "🎉 If you see this, your webhook is working!",
                "color": "Good",
                "weight": "Bolder",
                "wrap": True
            }
        ]
    }

    # Workflows expects the card wrapped in message/attachments
    payload = {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "contentUrl": None,
                "content": test_card
            }
        ]
    }

    print(f"Sending test to Workflows webhook...")
    print(f"URL: {webhook_url[:60]}...")
    print()

    try:
        response = requests.post(
            webhook_url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=30,
        )

        print(f"Response status: {response.status_code}")

        if response.status_code == 202:
            print()
            print("=" * 50)
            print("✅ SUCCESS! Webhook accepted the request.")
            print("   Check your Teams channel for the test message.")
            print("=" * 50)
            return True
        elif response.status_code == 200:
            print()
            print("=" * 50)
            print("✅ SUCCESS! Webhook returned 200 OK.")
            print("   Check your Teams channel for the test message.")
            print("=" * 50)
            return True
        else:
            print(f"Response body: {response.text[:300]}")
            print()
            print("=" * 50)
            print(f"❌ FAILED: Unexpected status {response.status_code}")
            print("=" * 50)
            return False

    except requests.exceptions.Timeout:
        print()
        print("=" * 50)
        print("⚠️  Request timed out after 30 seconds.")
        print("   Workflows can be slow - check Teams anyway.")
        print("=" * 50)
        return False
    except requests.exceptions.ConnectionError as e:
        print()
        print("=" * 50)
        print(f"❌ Connection error: {e}")
        print("   Check that the URL is correct and accessible.")
        print("=" * 50)
        return False
    except Exception as e:
        print()
        print("=" * 50)
        print(f"❌ Error: {e}")
        print("=" * 50)
        return False


def main():
    # Get webhook URL from argument or environment
    if len(sys.argv) > 1:
        url = sys.argv[1]
    else:
        url = os.getenv("TEAMS_WEBHOOK_URL")

    if not url:
        print("Teams Workflows Webhook Test")
        print("=" * 50)
        print()
        print("Usage:")
        print('  python test_teams_webhook.py "YOUR_WEBHOOK_URL"')
        print()
        print("Or set environment variable:")
        print('  export TEAMS_WEBHOOK_URL="YOUR_WEBHOOK_URL"')
        print("  python test_teams_webhook.py")
        print()
        print("To get your webhook URL:")
        print("  1. In Teams, go to your channel")
        print("  2. Click ... > Workflows")
        print('  3. Search "Post to a channel when a webhook request is received"')
        print("  4. Select team/channel and create")
        print("  5. Copy the URL")
        print()
        sys.exit(1)

    # Validate URL format
    if not url.startswith("https://"):
        print("❌ Error: Webhook URL must start with https://")
        sys.exit(1)

    if "logic.azure.com" not in url and "powerautomate" not in url:
        print("⚠️  Warning: URL doesn't look like a Workflows webhook.")
        print("   Expected: https://prod-XX.westus.logic.azure.com/...")
        print("   Got: " + url[:50] + "...")
        print()
        response = input("Continue anyway? (y/n): ")
        if response.lower() != 'y':
            sys.exit(1)

    success = test_webhook(url)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
