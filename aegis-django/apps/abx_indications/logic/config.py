"""Configuration for ABX Indication Monitoring."""

from django.conf import settings

_SETTINGS = getattr(settings, 'ABX_INDICATIONS', {})


class Config:
    LLM_MODEL = _SETTINGS.get('LLM_MODEL', 'qwen2.5:7b')
    OLLAMA_BASE_URL = _SETTINGS.get('OLLAMA_BASE_URL', 'http://localhost:11434')
    FHIR_BASE_URL = _SETTINGS.get('FHIR_BASE_URL', 'http://localhost:8081/fhir')
    LOOKBACK_HOURS = _SETTINGS.get('LOOKBACK_HOURS', 24)
    AUTO_ACCEPT_HOURS = _SETTINGS.get('AUTO_ACCEPT_HOURS', 48)
    POLL_INTERVAL_SECONDS = _SETTINGS.get('POLL_INTERVAL_SECONDS', 300)
    MONITORED_MEDICATIONS = _SETTINGS.get('MONITORED_MEDICATIONS', {})
