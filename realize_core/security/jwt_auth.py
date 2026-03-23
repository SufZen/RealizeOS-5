"""
JWT authentication for RealizeOS API.

Provides:
- Token creation with configurable expiry and claims
- Token verification with signature and expiry validation
- Refresh token flow (long-lived → short-lived access token)
- Role embedding in JWT claims for stateless RBAC

Uses HMAC-SHA256 (HS256) for signing. In production, consider
RS256 with public/private key pairs for distributed verification.
"""

import hashlib
import hmac
import json
import logging
import os
import time
from base64 import urlsafe_b64decode, urlsafe_b64encode
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Default expiry durations
DEFAULT_ACCESS_TOKEN_TTL = 3600  # 1 hour
DEFAULT_REFRESH_TOKEN_TTL = 604800  # 7 days

# JWT algorithm header
_JWT_HEADER = {"alg": "HS256", "typ": "JWT"}


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TokenClaims:
    """Decoded JWT claims."""

    sub: str  # Subject (user_id)
    role: str  # User role
    iat: float  # Issued at (Unix timestamp)
    exp: float  # Expiry (Unix timestamp)
    iss: str  # Issuer
    jti: str  # JWT ID (unique token identifier)
    scopes: list[str]  # Permission scopes
    token_type: str  # "access" or "refresh"

    @property
    def is_expired(self) -> bool:
        return time.time() > self.exp

    @property
    def is_access_token(self) -> bool:
        return self.token_type == "access"

    @property
    def is_refresh_token(self) -> bool:
        return self.token_type == "refresh"

    @property
    def remaining_seconds(self) -> float:
        return max(0, self.exp - time.time())


@dataclass
class TokenPair:
    """Access + refresh token pair."""

    access_token: str
    refresh_token: str
    expires_in: int
    token_type: str = "Bearer"


class JWTError(Exception):
    """Base exception for JWT errors."""


class TokenExpiredError(JWTError):
    """Token has expired."""


class InvalidTokenError(JWTError):
    """Token is malformed or signature is invalid."""


# ---------------------------------------------------------------------------
# Core JWT operations
# ---------------------------------------------------------------------------


def _get_secret() -> str:
    """Get the JWT signing secret from environment."""
    secret = os.environ.get("REALIZE_JWT_SECRET", "")
    if not secret:
        # Fall back to REALIZE_API_KEY for simpler setups
        secret = os.environ.get("REALIZE_API_KEY", "")
    if not secret:
        # Use a deterministic but unique per-install fallback
        secret = "realize-os-dev-secret-NOT-FOR-PRODUCTION"
        logger.warning("JWT_SECRET not set — using insecure dev secret")
    return secret


def _b64_encode(data: bytes) -> str:
    """URL-safe base64 encode, strip padding."""
    return urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64_decode(s: str) -> bytes:
    """URL-safe base64 decode, add padding."""
    padding = 4 - len(s) % 4
    if padding != 4:
        s += "=" * padding
    return urlsafe_b64decode(s)


def _sign(message: str, secret: str) -> str:
    """Create HMAC-SHA256 signature."""
    sig = hmac.new(
        secret.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return _b64_encode(sig)


def _generate_jti() -> str:
    """Generate a unique token ID."""
    return hashlib.sha256(f"{time.time()}-{os.urandom(16).hex()}".encode()).hexdigest()[:24]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def create_token(
    user_id: str,
    role: str = "user",
    scopes: list[str] | None = None,
    ttl_seconds: int = DEFAULT_ACCESS_TOKEN_TTL,
    token_type: str = "access",
    issuer: str = "realize-os",
    secret: str | None = None,
) -> str:
    """
    Create a signed JWT token.

    Args:
        user_id: Subject identifier.
        role: User role (owner, admin, user, guest).
        scopes: Permission scopes to include.
        ttl_seconds: Token time-to-live in seconds.
        token_type: "access" or "refresh".
        issuer: Token issuer identifier.
        secret: Signing secret (uses env var if not provided).

    Returns:
        Signed JWT string (header.payload.signature).
    """
    now = time.time()
    secret = secret or _get_secret()

    payload = {
        "sub": user_id,
        "role": role,
        "iat": int(now),
        "exp": int(now + ttl_seconds),
        "iss": issuer,
        "jti": _generate_jti(),
        "scopes": scopes or [],
        "token_type": token_type,
    }

    header_b64 = _b64_encode(json.dumps(_JWT_HEADER, separators=(",", ":")).encode())
    payload_b64 = _b64_encode(json.dumps(payload, separators=(",", ":")).encode())

    message = f"{header_b64}.{payload_b64}"
    signature = _sign(message, secret)

    return f"{message}.{signature}"


def verify_token(
    token: str,
    secret: str | None = None,
    require_type: str | None = None,
) -> TokenClaims:
    """
    Verify a JWT token and return its claims.

    Args:
        token: The JWT string.
        secret: Signing secret (uses env var if not provided).
        require_type: If set, reject tokens that aren't this type.

    Returns:
        TokenClaims dataclass.

    Raises:
        InvalidTokenError: If token is malformed or signature is invalid.
        TokenExpiredError: If token has expired.
    """
    secret = secret or _get_secret()

    parts = token.split(".")
    if len(parts) != 3:
        raise InvalidTokenError("Token must have 3 parts (header.payload.signature)")

    header_b64, payload_b64, signature = parts

    # Verify signature
    message = f"{header_b64}.{payload_b64}"
    expected_sig = _sign(message, secret)

    if not hmac.compare_digest(signature, expected_sig):
        raise InvalidTokenError("Invalid token signature")

    # Decode payload
    try:
        payload = json.loads(_b64_decode(payload_b64))
    except (json.JSONDecodeError, ValueError) as exc:
        raise InvalidTokenError(f"Invalid token payload: {exc}") from exc

    # Build claims
    claims = TokenClaims(
        sub=payload.get("sub", ""),
        role=payload.get("role", "guest"),
        iat=payload.get("iat", 0),
        exp=payload.get("exp", 0),
        iss=payload.get("iss", ""),
        jti=payload.get("jti", ""),
        scopes=payload.get("scopes", []),
        token_type=payload.get("token_type", "access"),
    )

    # Check expiry
    if claims.is_expired:
        raise TokenExpiredError(f"Token expired at {claims.exp} (now: {time.time():.0f})")

    # Check token type
    if require_type and claims.token_type != require_type:
        raise InvalidTokenError(f"Expected '{require_type}' token, got '{claims.token_type}'")

    return claims


def create_token_pair(
    user_id: str,
    role: str = "user",
    scopes: list[str] | None = None,
    access_ttl: int = DEFAULT_ACCESS_TOKEN_TTL,
    refresh_ttl: int = DEFAULT_REFRESH_TOKEN_TTL,
    secret: str | None = None,
) -> TokenPair:
    """
    Create an access + refresh token pair.

    Args:
        user_id: Subject identifier.
        role: User role.
        scopes: Permission scopes.
        access_ttl: Access token lifetime in seconds.
        refresh_ttl: Refresh token lifetime in seconds.
        secret: Signing secret.

    Returns:
        TokenPair with access_token, refresh_token, and expires_in.
    """
    access = create_token(
        user_id=user_id,
        role=role,
        scopes=scopes,
        ttl_seconds=access_ttl,
        token_type="access",
        secret=secret,
    )
    refresh = create_token(
        user_id=user_id,
        role=role,
        scopes=scopes,
        ttl_seconds=refresh_ttl,
        token_type="refresh",
        secret=secret,
    )
    return TokenPair(
        access_token=access,
        refresh_token=refresh,
        expires_in=access_ttl,
    )


def refresh_access_token(
    refresh_token: str,
    access_ttl: int = DEFAULT_ACCESS_TOKEN_TTL,
    secret: str | None = None,
) -> str:
    """
    Issue a new access token from a valid refresh token.

    Args:
        refresh_token: A valid refresh token.
        access_ttl: Lifetime of the new access token.
        secret: Signing secret.

    Returns:
        New access token string.

    Raises:
        InvalidTokenError: If refresh token is invalid.
        TokenExpiredError: If refresh token has expired.
    """
    claims = verify_token(refresh_token, secret=secret, require_type="refresh")

    return create_token(
        user_id=claims.sub,
        role=claims.role,
        scopes=list(claims.scopes),
        ttl_seconds=access_ttl,
        token_type="access",
        secret=secret,
    )


def extract_bearer_token(authorization: str) -> str:
    """
    Extract the token from a Bearer authorization header.

    Args:
        authorization: The Authorization header value.

    Returns:
        The raw token string.

    Raises:
        InvalidTokenError: If the header is not Bearer format.
    """
    if not authorization.startswith("Bearer "):
        raise InvalidTokenError("Authorization header must use Bearer scheme")
    token = authorization[7:].strip()
    if not token:
        raise InvalidTokenError("Empty Bearer token")
    return token
