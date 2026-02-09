"""DIRECT protocol client for NHSN submission.

Uses S/MIME encrypted email via HISP for CDA document submission.
"""

import logging
import smtplib
import ssl
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class DirectConfig:
    """Configuration for DIRECT protocol submission."""

    hisp_smtp_server: str = ""
    hisp_smtp_port: int = 587
    hisp_smtp_username: str = ""
    hisp_smtp_password: str = ""
    hisp_use_tls: bool = True
    sender_direct_address: str = ""
    nhsn_direct_address: str = ""
    facility_id: str = ""
    facility_name: str = ""
    timeout_seconds: int = 60

    def is_configured(self) -> bool:
        return all([
            self.hisp_smtp_server,
            self.hisp_smtp_username,
            self.hisp_smtp_password,
            self.sender_direct_address,
            self.nhsn_direct_address,
        ])

    def get_missing_config(self) -> list[str]:
        missing = []
        if not self.hisp_smtp_server:
            missing.append("HISP SMTP server")
        if not self.hisp_smtp_username:
            missing.append("HISP SMTP username")
        if not self.hisp_smtp_password:
            missing.append("HISP SMTP password")
        if not self.sender_direct_address:
            missing.append("Sender DIRECT address")
        if not self.nhsn_direct_address:
            missing.append("NHSN DIRECT address")
        return missing


@dataclass
class DirectSubmissionResult:
    """Result of a DIRECT submission attempt."""

    success: bool = False
    message_id: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    documents_sent: int = 0
    error_message: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "message_id": self.message_id,
            "timestamp": self.timestamp.isoformat(),
            "documents_sent": self.documents_sent,
            "error_message": self.error_message,
            "details": self.details,
        }


class DirectClient:
    """Client for DIRECT protocol submission to NHSN."""

    def __init__(self, config: DirectConfig):
        self.config = config

    def test_connection(self) -> tuple[bool, str]:
        """Test the HISP SMTP connection."""
        if not self.config.is_configured():
            missing = self.config.get_missing_config()
            return False, f"Missing configuration: {', '.join(missing)}"
        try:
            with self._get_smtp_connection() as server:
                return True, "Connection successful"
        except smtplib.SMTPAuthenticationError as e:
            return False, f"Authentication failed: {e}"
        except smtplib.SMTPConnectError as e:
            return False, f"Connection failed: {e}"
        except Exception as e:
            return False, f"Error: {e}"

    def submit_cda_documents(
        self,
        cda_documents: list[str],
        submission_type: str = "HAI-BSI",
        preparer_name: str = "",
        notes: str = "",
    ) -> DirectSubmissionResult:
        """Submit CDA documents to NHSN via DIRECT protocol."""
        result = DirectSubmissionResult()

        if not self.config.is_configured():
            missing = self.config.get_missing_config()
            result.error_message = f"DIRECT not configured: {', '.join(missing)}"
            return result

        if not cda_documents:
            result.error_message = "No CDA documents provided"
            return result

        try:
            msg = self._create_message(cda_documents, submission_type, preparer_name, notes)
            result.message_id = msg["Message-ID"]

            with self._get_smtp_connection() as server:
                server.send_message(msg)

            result.success = True
            result.documents_sent = len(cda_documents)
            result.details = {
                "submission_type": submission_type,
                "preparer": preparer_name,
                "recipient": self.config.nhsn_direct_address,
            }
            logger.info(
                f"DIRECT submission successful: {len(cda_documents)} documents, "
                f"Message-ID: {result.message_id}"
            )
        except smtplib.SMTPAuthenticationError as e:
            result.error_message = f"HISP authentication failed: {e}"
            logger.error(f"DIRECT authentication error: {e}")
        except smtplib.SMTPRecipientsRefused as e:
            result.error_message = f"NHSN address rejected: {e}"
            logger.error(f"DIRECT recipient refused: {e}")
        except smtplib.SMTPException as e:
            result.error_message = f"SMTP error: {e}"
            logger.error(f"DIRECT SMTP error: {e}")
        except Exception as e:
            result.error_message = f"Submission failed: {e}"
            logger.error(f"DIRECT submission error: {e}")

        return result

    def _get_smtp_connection(self) -> smtplib.SMTP:
        server = smtplib.SMTP(
            self.config.hisp_smtp_server,
            self.config.hisp_smtp_port,
            timeout=self.config.timeout_seconds,
        )
        if self.config.hisp_use_tls:
            context = ssl.create_default_context()
            server.starttls(context=context)
        server.login(self.config.hisp_smtp_username, self.config.hisp_smtp_password)
        return server

    def _create_message(
        self, cda_documents, submission_type, preparer_name, notes,
    ) -> MIMEMultipart:
        msg = MIMEMultipart()
        msg["From"] = self.config.sender_direct_address
        msg["To"] = self.config.nhsn_direct_address
        msg["Subject"] = (
            f"NHSN {submission_type} Submission - "
            f"{self.config.facility_name} ({self.config.facility_id})"
        )
        msg["Message-ID"] = f"<{uuid.uuid4()}@{self.config.sender_direct_address.split('@')[-1]}>"

        body = (
            f"NHSN Healthcare Associated Infection Data Submission\n\n"
            f"Facility: {self.config.facility_name}\n"
            f"Facility ID: {self.config.facility_id}\n"
            f"Submission Type: {submission_type}\n"
            f"Documents: {len(cda_documents)}\n"
            f"Submitted: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Prepared by: {preparer_name or 'System'}\n\n"
            f"{notes if notes else ''}\n\n"
            f"This message was automatically generated by the AEGIS NHSN Reporting Module.\n"
        )
        msg.attach(MIMEText(body, "plain"))

        for i, cda_xml in enumerate(cda_documents, 1):
            attachment = MIMEBase("application", "xml")
            attachment.set_payload(cda_xml.encode("utf-8"))
            encoders.encode_base64(attachment)
            attachment.add_header("Content-Disposition", f"attachment; filename=hai_report_{i:03d}.xml")
            attachment.add_header("Content-Type", "application/xml; charset=utf-8")
            msg.attach(attachment)

        return msg
