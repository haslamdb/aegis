"""Epic FHIR client with OAuth 2.0 JWT bearer token flow.

Implements the backend-services authorization profile used by Epic's
FHIR API. Uses RS384 signed JWT assertions to obtain access tokens.
"""

import time
from datetime import datetime, timedelta

import requests
from django.conf import settings

from .base import BaseFHIRClient


class EpicFHIRClient(BaseFHIRClient):
    """Client for Epic FHIR API with OAuth 2.0 backend auth.

    Uses JWT bearer token flow (RS384) for service-to-service auth.
    Tokens are cached and refreshed automatically.

    Args:
        base_url: Epic FHIR base URL. Defaults to settings.EPIC_FHIR_BASE_URL.
        client_id: OAuth client ID. Defaults to settings.EPIC_CLIENT_ID.
        private_key_path: Path to RSA private key file.
                          Defaults to settings.EPIC_PRIVATE_KEY_PATH.
        token_url: Token endpoint URL. If not provided, derived from base_url.
        timeout: Request timeout in seconds. Defaults to 30.
    """

    def __init__(
        self,
        base_url: str | None = None,
        client_id: str | None = None,
        private_key_path: str | None = None,
        token_url: str | None = None,
        timeout: int = 30,
    ):
        self.base_url = (base_url or getattr(
            settings, 'EPIC_FHIR_BASE_URL', ''
        )).rstrip("/")
        self.client_id = client_id or getattr(settings, 'EPIC_CLIENT_ID', '')
        self.private_key_path = private_key_path or getattr(
            settings, 'EPIC_PRIVATE_KEY_PATH', ''
        )
        self._token_url = token_url or getattr(settings, 'EPIC_TOKEN_URL', '')
        self.timeout = timeout

        self.access_token: str | None = None
        self.token_expires_at: datetime | None = None

        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/fhir+json",
            "Content-Type": "application/fhir+json",
        })

        # Load private key
        self.private_key: str | None = None
        if self.private_key_path:
            with open(self.private_key_path) as f:
                self.private_key = f.read()

    def _get_token_url(self) -> str:
        """Get or derive the OAuth token endpoint URL."""
        if self._token_url:
            return self._token_url
        # Derive from FHIR base URL (Epic convention)
        base = self.base_url.rsplit("/FHIR", 1)[0]
        return f"{base}/oauth2/token"

    def _get_access_token(self) -> str:
        """Obtain or return cached OAuth 2.0 access token.

        Uses JWT bearer flow for backend service authentication.
        Caches token and refreshes 60 seconds before expiry.

        Returns:
            Valid access token string.

        Raises:
            ValueError: If private key is not loaded.
            ImportError: If PyJWT is not installed.
        """
        # Return cached token if still valid
        if self.access_token and self.token_expires_at:
            if self.token_expires_at > datetime.now():
                return self.access_token

        if not self.private_key:
            raise ValueError("Private key not loaded - cannot authenticate to Epic")

        try:
            import jwt
        except ImportError:
            raise ImportError(
                "PyJWT is required for Epic OAuth. Install it with: "
                "pip install PyJWT[crypto]"
            )

        token_url = self._get_token_url()
        now = int(time.time())

        # Build JWT assertion
        claims = {
            "iss": self.client_id,
            "sub": self.client_id,
            "aud": token_url,
            "jti": f"{now}-{self.client_id}",
            "exp": now + 300,  # 5 minute expiry
        }

        assertion = jwt.encode(claims, self.private_key, algorithm="RS384")

        # Request access token
        response = requests.post(
            token_url,
            data={
                "grant_type": "client_credentials",
                "client_assertion_type": (
                    "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"
                ),
                "client_assertion": assertion,
            },
            timeout=self.timeout,
        )
        response.raise_for_status()

        token_data = response.json()
        self.access_token = token_data["access_token"]
        expires_in = token_data.get("expires_in", 3600)
        self.token_expires_at = datetime.now() + timedelta(seconds=expires_in - 60)

        return self.access_token

    def get(self, resource_path: str, params: dict | None = None) -> dict:
        """GET request with OAuth authentication."""
        token = self._get_access_token()
        response = self.session.get(
            f"{self.base_url}/{resource_path}",
            params=params,
            headers={"Authorization": f"Bearer {token}"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def post(self, resource_path: str, resource: dict) -> dict:
        """POST request with OAuth authentication."""
        token = self._get_access_token()
        response = self.session.post(
            f"{self.base_url}/{resource_path}",
            json=resource,
            headers={"Authorization": f"Bearer {token}"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()
