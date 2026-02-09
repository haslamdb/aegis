"""Configuration helper for NHSN Reporting module.

Reads from Django settings.NHSN_REPORTING dict.
"""

from django.conf import settings


def get_config():
    """Get NHSN_REPORTING config dict from settings."""
    return getattr(settings, 'NHSN_REPORTING', {})


def get_clarity_connection_string():
    """Get Clarity connection string (real or mock).

    Priority:
    1. CLARITY_CONNECTION_STRING (production Clarity)
    2. MOCK_CLARITY_DB_PATH as sqlite:/// (development)
    3. None if neither configured
    """
    cfg = get_config()
    conn = cfg.get('CLARITY_CONNECTION_STRING')
    if conn:
        return conn
    mock_path = cfg.get('MOCK_CLARITY_DB_PATH')
    if mock_path:
        from pathlib import Path
        if Path(mock_path).exists():
            return f"sqlite:///{mock_path}"
    return None


def is_clarity_configured():
    """Check if Clarity database is available."""
    return get_clarity_connection_string() is not None


def get_facility_id():
    """Get NHSN facility ID."""
    return get_config().get('NHSN_FACILITY_ID') or ''


def get_facility_name():
    """Get NHSN facility name."""
    return get_config().get('NHSN_FACILITY_NAME') or ''


def get_au_location_types():
    """Get AU reporting location types."""
    return get_config().get('AU_LOCATION_TYPES', ['ICU', 'Ward', 'NICU', 'BMT'])


def get_au_include_oral():
    """Whether to include oral antimicrobials in AU reporting."""
    return get_config().get('AU_INCLUDE_ORAL', True)


def get_ar_specimen_types():
    """Get AR specimen types to include."""
    return get_config().get('AR_SPECIMEN_TYPES', ['Blood', 'Urine', 'Respiratory', 'CSF'])


def get_ar_first_isolate_only():
    """Whether to apply first-isolate deduplication rule."""
    return get_config().get('AR_FIRST_ISOLATE_ONLY', True)


def is_direct_configured():
    """Check if DIRECT protocol submission is configured."""
    cfg = get_config()
    return all([
        cfg.get('DIRECT_HISP_SERVER'),
        cfg.get('DIRECT_HISP_USERNAME'),
        cfg.get('DIRECT_HISP_PASSWORD'),
        cfg.get('DIRECT_SENDER_ADDRESS'),
        cfg.get('DIRECT_NHSN_ADDRESS'),
    ])


def get_direct_config():
    """Get DIRECT protocol settings as a dict."""
    cfg = get_config()
    return {
        'hisp_smtp_server': cfg.get('DIRECT_HISP_SERVER') or '',
        'hisp_smtp_port': cfg.get('DIRECT_HISP_PORT', 587),
        'hisp_smtp_username': cfg.get('DIRECT_HISP_USERNAME') or '',
        'hisp_smtp_password': cfg.get('DIRECT_HISP_PASSWORD') or '',
        'sender_direct_address': cfg.get('DIRECT_SENDER_ADDRESS') or '',
        'nhsn_direct_address': cfg.get('DIRECT_NHSN_ADDRESS') or '',
        'facility_id': get_facility_id(),
        'facility_name': get_facility_name(),
    }
