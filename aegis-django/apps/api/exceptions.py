"""
PHI-safe exception handler for AEGIS API.

Strips potentially sensitive information from error responses
while preserving useful debugging context for developers.
"""

import logging

from rest_framework.views import exception_handler

logger = logging.getLogger('apps.api')

# Field names that might contain PHI
PHI_FIELDS = frozenset({
    'patient_mrn', 'patient_name', 'patient_id', 'patient_location',
    'mrn', 'name', 'ssn', 'dob', 'date_of_birth', 'address',
    'phone', 'email', 'ip_address',
})


def phi_safe_exception_handler(exc, context):
    """
    Custom exception handler that prevents PHI leakage in error responses.

    - Uses DRF's default handler for standard error formatting
    - Scrubs any PHI field names from validation error details
    - Logs the full error server-side for debugging
    """
    response = exception_handler(exc, context)

    if response is not None:
        # Log full error details server-side
        view = context.get('view')
        view_name = view.__class__.__name__ if view else 'unknown'
        logger.warning(
            'API error in %s: %s (status %s)',
            view_name, exc, response.status_code,
        )

        # Scrub PHI from validation error details
        if isinstance(response.data, dict):
            _scrub_phi_fields(response.data)

    return response


def _scrub_phi_fields(data):
    """Remove PHI field values from error detail dicts."""
    if not isinstance(data, dict):
        return
    for key in list(data.keys()):
        if key.lower() in PHI_FIELDS:
            data[key] = ['This field has an error.']
