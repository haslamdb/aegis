"""Notification delivery receipt tracking.

Tracks the delivery status of notifications sent through all channels
(email, SMS, Teams) to ensure delivery confirmation and enable
delivery analytics.
"""

import json
import logging
import os
import sqlite3
from datetime import datetime, date, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = os.path.expanduser("~/.aegis/notification_receipts.db")


class DeliveryStatus(Enum):
    """Status of a notification delivery."""
    QUEUED = "queued"           # Created, not yet sent
    SENT = "sent"               # Sent to delivery service
    DELIVERED = "delivered"     # Confirmed delivered
    FAILED = "failed"           # Delivery failed
    BOUNCED = "bounced"         # Delivery bounced
    READ = "read"               # Recipient opened/read


class NotificationChannel(Enum):
    """Available notification channels."""
    EMAIL = "email"
    SMS = "sms"
    TEAMS = "teams"
    WEBHOOK = "webhook"


RECEIPT_SCHEMA = """
CREATE TABLE IF NOT EXISTS delivery_receipts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Notification identification
    notification_id TEXT NOT NULL,     -- UUID for the notification
    alert_id TEXT,                     -- Related alert ID (if applicable)

    -- Channel details
    channel TEXT NOT NULL,             -- email, sms, teams, webhook
    recipient TEXT,                    -- Email address, phone number, channel ID

    -- Content summary
    subject TEXT,                      -- Notification subject/title
    notification_type TEXT,            -- alert, summary, escalation, etc.

    -- Delivery status
    status TEXT NOT NULL DEFAULT 'queued',

    -- Timing
    queued_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    sent_at TIMESTAMP,
    delivered_at TIMESTAMP,
    read_at TIMESTAMP,
    failed_at TIMESTAMP,

    -- Error tracking
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,

    -- External IDs
    external_id TEXT,                  -- Message ID from delivery service

    -- Metadata
    metadata TEXT,                     -- JSON blob for channel-specific data

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_receipt_notification ON delivery_receipts(notification_id);
CREATE INDEX IF NOT EXISTS idx_receipt_alert ON delivery_receipts(alert_id);
CREATE INDEX IF NOT EXISTS idx_receipt_channel ON delivery_receipts(channel);
CREATE INDEX IF NOT EXISTS idx_receipt_status ON delivery_receipts(status);
CREATE INDEX IF NOT EXISTS idx_receipt_queued ON delivery_receipts(queued_at);
CREATE INDEX IF NOT EXISTS idx_receipt_recipient ON delivery_receipts(recipient);
"""


class ReceiptTracker:
    """Tracks notification delivery receipts across all channels."""

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or os.environ.get(
            "NOTIFICATION_RECEIPT_DB_PATH", DEFAULT_DB_PATH
        )
        self._ensure_db()

    def _ensure_db(self):
        """Create database and tables if they don't exist."""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(RECEIPT_SCHEMA)

    def _connect(self):
        """Get database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def record_send(
        self,
        notification_id: str,
        channel: str,
        recipient: str,
        subject: str | None = None,
        notification_type: str | None = None,
        alert_id: str | None = None,
        metadata: dict | None = None,
    ) -> int:
        """Record a notification being sent.

        Returns the receipt ID.
        """
        now = datetime.now()
        with self._connect() as conn:
            cursor = conn.execute(
                """INSERT INTO delivery_receipts
                (notification_id, alert_id, channel, recipient, subject,
                 notification_type, status, queued_at, sent_at, metadata, created_at)
                VALUES (?, ?, ?, ?, ?, ?, 'sent', ?, ?, ?, ?)""",
                (
                    notification_id, alert_id, channel, recipient, subject,
                    notification_type, now.isoformat(), now.isoformat(),
                    json.dumps(metadata) if metadata else None,
                    now.isoformat(),
                )
            )
            return cursor.lastrowid

    def update_status(
        self,
        receipt_id: int | None = None,
        notification_id: str | None = None,
        status: str = "delivered",
        error_message: str | None = None,
        external_id: str | None = None,
    ) -> bool:
        """Update delivery status of a notification.

        Can look up by receipt_id or notification_id.
        """
        now = datetime.now()

        # Build the time field to update based on status
        time_field = {
            "delivered": "delivered_at",
            "read": "read_at",
            "failed": "failed_at",
            "bounced": "failed_at",
        }.get(status)

        with self._connect() as conn:
            if receipt_id:
                where = "id = ?"
                params = [receipt_id]
            elif notification_id:
                where = "notification_id = ?"
                params = [notification_id]
            else:
                return False

            updates = ["status = ?"]
            values = [status]

            if time_field:
                updates.append(f"{time_field} = ?")
                values.append(now.isoformat())

            if error_message:
                updates.append("error_message = ?")
                values.append(error_message)

            if external_id:
                updates.append("external_id = ?")
                values.append(external_id)

            if status in ("failed", "bounced"):
                updates.append("retry_count = retry_count + 1")

            values.extend(params)

            result = conn.execute(
                f"UPDATE delivery_receipts SET {', '.join(updates)} WHERE {where}",
                values
            )
            return result.rowcount > 0

    def get_receipt(self, receipt_id: int) -> dict | None:
        """Get a single receipt by ID."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM delivery_receipts WHERE id = ?", (receipt_id,)
            ).fetchone()
            return dict(row) if row else None

    def get_receipts_for_alert(self, alert_id: str) -> list[dict]:
        """Get all delivery receipts for an alert."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM delivery_receipts WHERE alert_id = ? ORDER BY created_at DESC",
                (alert_id,)
            ).fetchall()
            return [dict(row) for row in rows]

    def get_delivery_stats(self, days: int = 30) -> dict[str, Any]:
        """Get delivery statistics across all channels.

        Returns:
            Dict with total_sent, delivery_rate, failure_rate,
            avg_delivery_time, by_channel breakdown
        """
        cutoff = (date.today() - timedelta(days=days)).isoformat()

        with self._connect() as conn:
            # Total sent
            total = conn.execute(
                "SELECT COUNT(*) FROM delivery_receipts WHERE date(created_at) >= ?",
                (cutoff,)
            ).fetchone()[0]

            if total == 0:
                return {
                    "total_sent": 0,
                    "delivered": 0, "failed": 0, "read": 0,
                    "delivery_rate": None, "failure_rate": None, "read_rate": None,
                    "by_channel": {},
                }

            # Breakdown by status
            status_rows = conn.execute(
                """SELECT status, COUNT(*) as cnt
                FROM delivery_receipts WHERE date(created_at) >= ?
                GROUP BY status""",
                (cutoff,)
            ).fetchall()
            by_status = {row["status"]: row["cnt"] for row in status_rows}

            delivered = by_status.get("delivered", 0) + by_status.get("read", 0)
            failed = by_status.get("failed", 0) + by_status.get("bounced", 0)
            read_count = by_status.get("read", 0)

            # By channel breakdown
            channel_rows = conn.execute(
                """SELECT channel,
                    COUNT(*) as total,
                    SUM(CASE WHEN status IN ('delivered', 'read') THEN 1 ELSE 0 END) as delivered,
                    SUM(CASE WHEN status IN ('failed', 'bounced') THEN 1 ELSE 0 END) as failed
                FROM delivery_receipts WHERE date(created_at) >= ?
                GROUP BY channel""",
                (cutoff,)
            ).fetchall()

            by_channel = {}
            for row in channel_rows:
                ch_total = row["total"]
                by_channel[row["channel"]] = {
                    "total": ch_total,
                    "delivered": row["delivered"],
                    "failed": row["failed"],
                    "delivery_rate": round(row["delivered"] / ch_total * 100, 1) if ch_total > 0 else None,
                }

            return {
                "total_sent": total,
                "delivered": delivered,
                "failed": failed,
                "read": read_count,
                "delivery_rate": round(delivered / total * 100, 1) if total > 0 else None,
                "failure_rate": round(failed / total * 100, 1) if total > 0 else None,
                "read_rate": round(read_count / total * 100, 1) if total > 0 else None,
                "by_channel": by_channel,
            }

    def get_failed_notifications(self, days: int = 7, limit: int = 50) -> list[dict]:
        """Get recent failed notifications for retry/investigation."""
        cutoff = (date.today() - timedelta(days=days)).isoformat()

        with self._connect() as conn:
            rows = conn.execute(
                """SELECT * FROM delivery_receipts
                WHERE status IN ('failed', 'bounced') AND date(created_at) >= ?
                ORDER BY created_at DESC LIMIT ?""",
                (cutoff, limit)
            ).fetchall()
            return [dict(row) for row in rows]
