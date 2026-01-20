"""Firebase JWT Verifier for FastMCP"""

import logging

import firebase_admin
from fastmcp.server.auth.auth import AccessToken, AuthProvider
from firebase_admin import auth as firebase_auth
from firebase_admin import credentials, initialize_app

logger = logging.getLogger(__name__)


class FirebaseJWTVerifier(AuthProvider):
    """Verifies Firebase ID tokens."""

    def __init__(
        self,
        project_id: str,
        private_key_id: str | None = None,
        private_key: str | None = None,
        client_email: str | None = None,
        client_id: str | None = None,
        client_x509_cert_url: str | None = None,
    ):
        super().__init__()
        self.project_id = project_id
        self.app_name = f"firebase_verifier_{project_id}"

        self.service_account_info = {
            "type": "service_account",
            "project_id": self.project_id,
            "private_key_id": private_key_id,
            "private_key": private_key,
            "client_email": client_email,
            "client_id": client_id,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_x509_cert_url": client_x509_cert_url,
        }

        self._initialize_firebase()

    def _initialize_firebase(self):
        """Initialize Firebase Admin SDK for token verification only."""
        try:
            firebase_admin.get_app(name=self.app_name)
            logger.info(f"Firebase app '{self.app_name}' already initialized")
        except ValueError:
            cred = credentials.Certificate(self.service_account_info)
            initialize_app(cred, name=self.app_name)
            logger.info(f"Firebase initialized for verification (project: {self.project_id})")

    async def verify_token(self, token: str):
        """Verify Firebase ID token."""
        try:
            app = firebase_admin.get_app(name=self.app_name)
            firebase_auth.verify_id_token(token, app=app)

            # NOTE: This makes an assumption that the JWT token from Firebase
            # _always_ has a verified e-mail address. For Gather, we either
            # authenticate via OAuth or one-time password, for which this is true.

            return AccessToken(
                token=token,
                client_id="firebase",
                scopes=[],
            )

        except Exception as e:
            logger.debug(f"Firebase token verification failed: {e}")
            return None
