"""Configuration management for ASP Bacteremia Alerts."""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)
else:
    # Fall back to template for defaults
    template_path = Path(__file__).parent.parent / ".env.template"
    if template_path.exists():
        load_dotenv(template_path)


class Config:
    """Application configuration."""

    # FHIR Server settings
    FHIR_BASE_URL: str = os.getenv("FHIR_BASE_URL", "http://localhost:8080/fhir")

    # Epic FHIR settings (for production)
    EPIC_FHIR_BASE_URL: str | None = os.getenv("EPIC_FHIR_BASE_URL")
    EPIC_CLIENT_ID: str | None = os.getenv("EPIC_CLIENT_ID")
    EPIC_PRIVATE_KEY_PATH: str | None = os.getenv("EPIC_PRIVATE_KEY_PATH")

    # Alerting settings
    ALERT_EMAIL_TO: str = os.getenv("ALERT_EMAIL_TO", "")
    SMTP_SERVER: str = os.getenv("SMTP_SERVER", "localhost")

    # Polling settings
    POLL_INTERVAL: int = int(os.getenv("POLL_INTERVAL", "300"))

    @classmethod
    def is_epic_configured(cls) -> bool:
        """Check if Epic FHIR credentials are configured."""
        return bool(cls.EPIC_FHIR_BASE_URL and cls.EPIC_CLIENT_ID)

    @classmethod
    def get_fhir_base_url(cls) -> str:
        """Get the appropriate FHIR base URL."""
        if cls.is_epic_configured():
            return cls.EPIC_FHIR_BASE_URL
        return cls.FHIR_BASE_URL


config = Config()
