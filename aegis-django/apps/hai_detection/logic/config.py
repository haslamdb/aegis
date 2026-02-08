"""Configuration adapter for HAI Detection module.

Reads from Django settings.HAI_DETECTION dict, falling back to
sensible defaults. This replaces the os.getenv()-based config
from the Flask version.

Usage in Django settings:
    HAI_DETECTION = {
        'NOTE_SOURCE': 'mock',
        'FHIR_BASE_URL': 'http://localhost:8081/fhir',
        'LLM_BACKEND': 'ollama',
        ...
    }
"""

from pathlib import Path

from django.conf import settings

_HAI_SETTINGS = getattr(settings, 'HAI_DETECTION', {})


class Config:
    """HAI Detection configuration backed by Django settings."""

    # --- Data Sources ---
    NOTE_SOURCE: str = _HAI_SETTINGS.get('NOTE_SOURCE', 'fhir')
    DEVICE_SOURCE: str = _HAI_SETTINGS.get('DEVICE_SOURCE', 'fhir')
    CULTURE_SOURCE: str = _HAI_SETTINGS.get('CULTURE_SOURCE', 'fhir')
    PROCEDURE_SOURCE: str = _HAI_SETTINGS.get('PROCEDURE_SOURCE', 'fhir')
    VENTILATOR_SOURCE: str = _HAI_SETTINGS.get('VENTILATOR_SOURCE', 'fhir')
    FHIR_BASE_URL: str = _HAI_SETTINGS.get('FHIR_BASE_URL', 'http://localhost:8081/fhir')
    CLARITY_CONNECTION_STRING: str | None = _HAI_SETTINGS.get('CLARITY_CONNECTION_STRING')

    # --- LLM Backend ---
    LLM_BACKEND: str = _HAI_SETTINGS.get('LLM_BACKEND', 'ollama')
    OLLAMA_BASE_URL: str = _HAI_SETTINGS.get('OLLAMA_BASE_URL', 'http://localhost:11434')
    OLLAMA_MODEL: str = _HAI_SETTINGS.get('OLLAMA_MODEL', 'llama3.3:70b')
    VLLM_BASE_URL: str = _HAI_SETTINGS.get('VLLM_BASE_URL', 'http://localhost:8000')
    VLLM_MODEL: str = _HAI_SETTINGS.get('VLLM_MODEL', 'Qwen/Qwen2.5-72B-Instruct')
    CLAUDE_API_KEY: str | None = _HAI_SETTINGS.get('CLAUDE_API_KEY')
    CLAUDE_MODEL: str = _HAI_SETTINGS.get('CLAUDE_MODEL', 'claude-sonnet-4-20250514')

    # --- Classification Thresholds ---
    AUTO_CLASSIFY_THRESHOLD: float = float(
        _HAI_SETTINGS.get('AUTO_CLASSIFY_THRESHOLD', 0.85)
    )
    IP_REVIEW_THRESHOLD: float = float(
        _HAI_SETTINGS.get('IP_REVIEW_THRESHOLD', 0.60)
    )

    # --- CLABSI Criteria ---
    MIN_DEVICE_DAYS: int = int(_HAI_SETTINGS.get('MIN_DEVICE_DAYS', 2))
    POST_REMOVAL_WINDOW_DAYS: int = int(_HAI_SETTINGS.get('POST_REMOVAL_WINDOW_DAYS', 1))

    # --- CAUTI Criteria ---
    CAUTI_MIN_CATHETER_DAYS: int = int(_HAI_SETTINGS.get('CAUTI_MIN_CATHETER_DAYS', 2))
    CAUTI_POST_REMOVAL_WINDOW_DAYS: int = int(_HAI_SETTINGS.get('CAUTI_POST_REMOVAL_WINDOW_DAYS', 1))
    CAUTI_MIN_CFU_THRESHOLD: int = int(_HAI_SETTINGS.get('CAUTI_MIN_CFU_THRESHOLD', 100000))

    # --- VAE Criteria ---
    VAE_MIN_VENT_DAYS: int = int(_HAI_SETTINGS.get('VAE_MIN_VENT_DAYS', 2))
    VAE_BASELINE_PERIOD_DAYS: int = int(_HAI_SETTINGS.get('VAE_BASELINE_PERIOD_DAYS', 2))
    VAE_PEEP_INCREASE_THRESHOLD: float = float(_HAI_SETTINGS.get('VAE_PEEP_INCREASE_THRESHOLD', 3.0))
    VAE_FIO2_INCREASE_THRESHOLD: float = float(_HAI_SETTINGS.get('VAE_FIO2_INCREASE_THRESHOLD', 20.0))

    # --- SSI Criteria ---
    SSI_DEFAULT_SURVEILLANCE_DAYS: int = int(_HAI_SETTINGS.get('SSI_DEFAULT_SURVEILLANCE_DAYS', 30))
    SSI_IMPLANT_SURVEILLANCE_DAYS: int = int(_HAI_SETTINGS.get('SSI_IMPLANT_SURVEILLANCE_DAYS', 90))

    # --- Database ---
    HAI_DB_PATH: str = _HAI_SETTINGS.get(
        'HAI_DB_PATH',
        str(Path.home() / '.aegis' / 'nhsn.db'),
    )
    ALERT_DB_PATH: str = _HAI_SETTINGS.get(
        'ALERT_DB_PATH',
        str(Path.home() / '.aegis' / 'alerts.db'),
    )
    MOCK_CLARITY_DB_PATH: str = _HAI_SETTINGS.get(
        'MOCK_CLARITY_DB_PATH',
        str(Path.home() / '.aegis' / 'mock_clarity.db'),
    )

    # --- Monitoring ---
    POLL_INTERVAL: int = int(_HAI_SETTINGS.get('POLL_INTERVAL', 300))
    LOOKBACK_HOURS: int = int(_HAI_SETTINGS.get('LOOKBACK_HOURS', 24))

    # --- Notifications ---
    TEAMS_WEBHOOK_URL: str | None = _HAI_SETTINGS.get('TEAMS_WEBHOOK_URL')
    DASHBOARD_BASE_URL: str = _HAI_SETTINGS.get('DASHBOARD_BASE_URL', 'http://localhost:8000')

    # --- Email Notifications ---
    SMTP_SERVER: str | None = _HAI_SETTINGS.get('SMTP_SERVER')
    SMTP_PORT: int = int(_HAI_SETTINGS.get('SMTP_PORT', 587))
    SMTP_USERNAME: str | None = _HAI_SETTINGS.get('SMTP_USERNAME')
    SMTP_PASSWORD: str | None = _HAI_SETTINGS.get('SMTP_PASSWORD')
    SENDER_EMAIL: str = _HAI_SETTINGS.get('SENDER_EMAIL', 'aegis-hai@example.com')
    SENDER_NAME: str = _HAI_SETTINGS.get('SENDER_NAME', 'AEGIS HAI Alerts')
    HAI_NOTIFICATION_EMAIL: str | None = _HAI_SETTINGS.get('HAI_NOTIFICATION_EMAIL')

    # --- Note Processing ---
    MAX_NOTE_LENGTH: int = int(_HAI_SETTINGS.get('MAX_NOTE_LENGTH', 50000))
    MAX_NOTES_PER_PATIENT: int = int(_HAI_SETTINGS.get('MAX_NOTES_PER_PATIENT', 20))

    # --- Epic FHIR (if using Epic) ---
    EPIC_CLIENT_ID: str | None = _HAI_SETTINGS.get('EPIC_CLIENT_ID')
    EPIC_PRIVATE_KEY_PATH: str | None = _HAI_SETTINGS.get('EPIC_PRIVATE_KEY_PATH')
    EPIC_FHIR_BASE_URL: str | None = _HAI_SETTINGS.get('EPIC_FHIR_BASE_URL')

    @classmethod
    def get_fhir_base_url(cls) -> str:
        """Get the FHIR base URL (Epic if configured, otherwise default)."""
        if cls.EPIC_FHIR_BASE_URL and cls.EPIC_CLIENT_ID:
            return cls.EPIC_FHIR_BASE_URL
        return cls.FHIR_BASE_URL

    @classmethod
    def is_ollama_configured(cls) -> bool:
        return cls.LLM_BACKEND == 'ollama' and bool(cls.OLLAMA_BASE_URL)

    @classmethod
    def is_vllm_configured(cls) -> bool:
        return cls.LLM_BACKEND == 'vllm' and bool(cls.VLLM_BASE_URL)

    @classmethod
    def is_claude_configured(cls) -> bool:
        return cls.LLM_BACKEND == 'claude' and bool(cls.CLAUDE_API_KEY)

    @classmethod
    def is_clarity_configured(cls) -> bool:
        return bool(cls.CLARITY_CONNECTION_STRING) or Path(cls.MOCK_CLARITY_DB_PATH).exists()

    @classmethod
    def get_clarity_connection_string(cls) -> str | None:
        if cls.CLARITY_CONNECTION_STRING:
            return cls.CLARITY_CONNECTION_STRING
        if Path(cls.MOCK_CLARITY_DB_PATH).exists():
            return f'sqlite:///{cls.MOCK_CLARITY_DB_PATH}'
        return None

    @classmethod
    def is_teams_configured(cls) -> bool:
        return bool(cls.TEAMS_WEBHOOK_URL)

    @classmethod
    def is_email_configured(cls) -> bool:
        return bool(cls.SMTP_SERVER) and bool(cls.HAI_NOTIFICATION_EMAIL)


# Module-level convenience instance
config = Config()
