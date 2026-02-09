"""
Configuration for surgical prophylaxis module.

Reads settings from Django's SURGICAL_PROPHYLAXIS config dict.
"""

from django.conf import settings


def _get_config():
    return getattr(settings, 'SURGICAL_PROPHYLAXIS', {})


class Config:
    """Configuration constants for surgical prophylaxis."""

    @staticmethod
    def get(key, default=None):
        return _get_config().get(key, default)

    # FHIR
    FHIR_BASE_URL = property(lambda self: _get_config().get('FHIR_BASE_URL', 'http://localhost:8081/fhir'))

    # HL7
    HL7_ENABLED = property(lambda self: _get_config().get('HL7_ENABLED', False))
    HL7_HOST = property(lambda self: _get_config().get('HL7_HOST', '0.0.0.0'))
    HL7_PORT = property(lambda self: _get_config().get('HL7_PORT', 2575))

    # Polling
    POLL_INTERVAL_SECONDS = property(lambda self: _get_config().get('POLL_INTERVAL_SECONDS', 300))
    FHIR_SCHEDULE_POLL_INTERVAL = property(lambda self: _get_config().get('FHIR_SCHEDULE_POLL_INTERVAL', 15))
    FHIR_PROPHYLAXIS_POLL_INTERVAL = property(lambda self: _get_config().get('FHIR_PROPHYLAXIS_POLL_INTERVAL', 5))
    FHIR_LOOKAHEAD_HOURS = property(lambda self: _get_config().get('FHIR_LOOKAHEAD_HOURS', 48))

    # Alert triggers
    ALERT_T24_ENABLED = property(lambda self: _get_config().get('ALERT_T24_ENABLED', True))
    ALERT_T2_ENABLED = property(lambda self: _get_config().get('ALERT_T2_ENABLED', True))
    ALERT_T60_ENABLED = property(lambda self: _get_config().get('ALERT_T60_ENABLED', True))
    ALERT_T0_ENABLED = property(lambda self: _get_config().get('ALERT_T0_ENABLED', True))

    # Channels
    EPIC_CHAT_ENABLED = property(lambda self: _get_config().get('EPIC_CHAT_ENABLED', False))
    TEAMS_ENABLED = property(lambda self: _get_config().get('TEAMS_ENABLED', False))

    # Timing thresholds (constants)
    STANDARD_TIMING_WINDOW = 60
    EXTENDED_TIMING_WINDOW = 120
    STANDARD_DURATION_HOURS = 24
    CARDIAC_DURATION_HOURS = 48

    EXTENDED_WINDOW_ANTIBIOTICS = [
        'vancomycin',
        'ciprofloxacin',
        'levofloxacin',
        'moxifloxacin',
    ]

    NO_REDOSE_ANTIBIOTICS = [
        'vancomycin',
        'metronidazole',
    ]
