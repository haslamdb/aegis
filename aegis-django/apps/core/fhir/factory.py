"""FHIR client factory.

Returns the appropriate FHIR client based on Django settings.
"""

from django.conf import settings

from .base import BaseFHIRClient, HAPIFHIRClient
from .oauth import EpicFHIRClient


def get_fhir_client(module_settings_key: str | None = None) -> BaseFHIRClient:
    """Create and return the appropriate FHIR client.

    Checks for Epic FHIR settings first. If present, returns an
    EpicFHIRClient. Otherwise returns a HAPIFHIRClient.

    Args:
        module_settings_key: Optional Django settings key (e.g.
            'GUIDELINE_ADHERENCE') whose dict may contain a
            module-specific 'FHIR_BASE_URL'.

    Returns:
        A configured BaseFHIRClient instance.
    """
    # Check for Epic settings
    epic_url = getattr(settings, 'EPIC_FHIR_BASE_URL', '')
    epic_client_id = getattr(settings, 'EPIC_CLIENT_ID', '')

    if epic_url and epic_client_id:
        return EpicFHIRClient()

    # Check for module-specific base URL
    base_url = None
    if module_settings_key:
        module_config = getattr(settings, module_settings_key, {})
        if isinstance(module_config, dict):
            base_url = module_config.get('FHIR_BASE_URL')

    return HAPIFHIRClient(base_url=base_url)
