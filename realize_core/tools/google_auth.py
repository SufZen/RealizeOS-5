"""
Google OAuth authentication for RealizeOS.

Loads OAuth credentials from configurable paths and auto-refreshes tokens.
"""

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# Google API scopes (must match what was authorized in the OAuth consent screen)
SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.settings.basic",
    "https://mail.google.com/",
    "https://www.googleapis.com/auth/spreadsheets",
]

_credentials = None

# Default paths (overridable via env vars)
_CREDENTIALS_DIR = Path(os.environ.get("GOOGLE_CREDENTIALS_DIR", ".credentials"))
_TOKENS_PATH = _CREDENTIALS_DIR / "tokens.json"
_CLIENT_SECRETS_PATH = _CREDENTIALS_DIR / "client_secrets.json"


def _load_client_config() -> dict:
    """Load client ID and secret from the OAuth credentials file."""
    path = Path(os.environ.get("GOOGLE_OAUTH_CREDENTIALS_PATH", str(_CLIENT_SECRETS_PATH)))
    if not path.exists():
        logger.debug(f"OAuth credentials file not found: {path}")
        return {}
    try:
        with open(path) as f:
            data = json.load(f)
        return data.get("installed", data.get("web", {}))
    except Exception as e:
        logger.error(f"Failed to parse OAuth credentials: {e}")
        return {}


def get_credentials():
    """
    Load and return valid Google OAuth credentials.
    Auto-refreshes the access token if expired.
    Returns None if credentials are not available.
    """
    global _credentials

    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
    except BaseException:
        logger.debug("google-auth not available, Google tools unavailable")
        return None

    if _credentials and _credentials.valid:
        return _credentials

    # Try multiple token paths
    tokens_path = Path(os.environ.get("GOOGLE_OAUTH_TOKENS_PATH", str(_TOKENS_PATH)))
    if not tokens_path.exists():
        # Fallback: Docker data volume
        docker_path = Path(os.environ.get("DATA_DIR", "/app/data")) / "tokens.json"
        if docker_path.exists():
            tokens_path = docker_path

    if not tokens_path.exists():
        logger.debug(f"Google OAuth tokens not found at {tokens_path}")
        return None

    try:
        with open(tokens_path) as f:
            token_data = json.load(f)

        client_config = _load_client_config()
        client_id = client_config.get("client_id")
        client_secret = client_config.get("client_secret")

        if not client_id or not client_secret:
            logger.error("Missing client_id or client_secret in OAuth credentials")
            return None

        _credentials = Credentials(
            token=token_data.get("access_token"),
            refresh_token=token_data.get("refresh_token"),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret,
            scopes=SCOPES,
        )

        if _credentials.expired and _credentials.refresh_token:
            logger.info("Access token expired, refreshing...")
            try:
                _credentials.refresh(Request())
                _save_tokens(_credentials, token_data, tokens_path)
            except Exception as refresh_err:
                # Clear stale credentials so next call doesn't use invalid ones
                _credentials = None
                err_msg = str(refresh_err)
                # Sanitize: don't log full tokens
                if "token" in err_msg.lower() and len(err_msg) > 100:
                    err_msg = err_msg[:100] + "..."
                logger.error(
                    f"Google token refresh failed (token may be revoked): {err_msg}. Re-run OAuth flow to re-authorize."
                )
                return None

        logger.info("Google credentials loaded successfully")
        return _credentials

    except Exception as e:
        # Don't leave invalid credentials cached
        _credentials = None
        logger.error(f"Failed to load Google credentials: {e}", exc_info=True)
        return None


def _save_tokens(creds, original_data: dict, path: Path):
    """Save refreshed tokens back to the tokens file."""
    try:
        original_data["access_token"] = creds.token
        if creds.expiry:
            original_data["expiry_date"] = int(creds.expiry.timestamp() * 1000)
        with open(path, "w") as f:
            json.dump(original_data, f, indent=2)
    except Exception as e:
        logger.warning(f"Failed to save refreshed token: {e}")
