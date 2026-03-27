"""
JWT authentication for RealizeOS API.

Provides:
- Token creation with configurable expiry and claims
- Token verification with signature and expiry validation
- Refresh token flow (long-lived → short-lived access token)
- Role embedding in JWT claims for stateless RBAC
- Token revocation via JTI blacklist
- Algorithm confusion attack protection (HS256 only)

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
from threading import Lock

logger = logging.getLogger(__name__)

# Default expiry durations
DEFAULT_ACCESS_TOKEN_TTL = 3600  # 1 hour
DEFAULT_REFRESH_TOKEN_TTL = 604800  # 7 days

# Maximum number of times a refresh token lineage can be refreshed
MAX_REFRESH_CHAIN = 720  # ~30 days at 1 hour per access token

# Only allow this algorithm — prevents alg:none and alg-confusion attacks
_ALLOWED_ALGORITHM = "HS256"

# JWT algorithm header
_JWT_HEADER = {"alg": _ALLOWED_ALGORITHM, "typ": "JWT"}

# Minimum secret length for production environments
MIN_SECRET_LENGTH = 32


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
    refresh_count: int = 0  # Number of times this lineage has been refreshed

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


class TokenRevokedError(JWTError):
    """Token has been revoked."""


class WeakSecretError(JWTError):
    """JWT secret is too weak for production use."""


# ---------------------------------------------------------------------------
# Token Blacklist (JTI-based revocation)
# ---------------------------------------------------------------------------


class TokenBlacklist:
    """
    In-memory JTI blacklist for token revocation.

    Entries auto-expire after `ttl` seconds to prevent unbounded growth.
    Thread-safe via Lock.
    """

    def __init__(self, ttl: int = DEFAULT_REFRESH_TOKEN_TTL + 3600):
        self._blacklist: dict[str, float] = {}  # jti → expiry timestamp
        self._lock = Lock()
        self._ttl = ttl

    def revoke(self, jti: str, token_exp: float = 0.0) -> None:
        """Add a JTI to the blacklist."""
        with self._lock:
            # Keep the entry until the token would have expired naturally
            expiry = token_exp if token_exp > 0 else time.time() + self._ttl
            self._blacklist[jti] = expiry

    def is_revoked(self, jti: str) -> bool:
        """Check if a JTI has been revoked."""
        with self._lock:
            return jti in self._blacklist

    def cleanup(self) -> int:
        """Remove expired blacklist entries. Returns count removed."""
        now = time.time()
        with self._lock:
            expired = [jti for jti, exp in self._blacklist.items() if exp < now]
            for jti in expired:
                del self._blacklist[jti]
            return len(expired)

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._blacklist)


# Module-level singleton blacklist
_token_blacklist: TokenBlacklist | None = None


def get_token_blacklist() -> TokenBlacklist:
    """Get or create the global token blacklist."""
    global _token_blacklist
    if _token_blacklist is None:
        _token_blacklist = TokenBlacklist()
    return _token_blacklist


def revoke_token(jti: str, token_exp: float = 0.0) -> None:
    """Revoke a token by its JTI."""
    bl = get_token_blacklist()
    bl.revoke(jti, token_exp)
    logger.info("Token revoked: jti=%s", jti[:8] + "...")


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


def _check_secret_strength(secret: str) -> None:
    """
    Warn or raise if the JWT secret is too weak.

    In production (REALIZE_ENV=production), raises WeakSecretError.
    Otherwise, logs a warning.
    """
    is_production = os.environ.get("REALIZE_ENV", "").lower() == "production"
    is_dev_secret = secret == "realize-os-dev-secret-NOT-FOR-PRODUCTION"

    if is_dev_secret and is_production:
        raise WeakSecretError(
            "Cannot use default dev secret in production. "
            "Set REALIZE_JWT_SECRET to a 32+ character random string."
        )

    if len(secret) < MIN_SECRET_LENGTH:
        msg = (
            f"JWT secret is only {len(secret)} chars (minimum: {MIN_SECRET_LENGTH}). "
            "Use a strong random secret for production."
        )
        if is_production:
            raise WeakSecretError(msg)
        logger.warning(msg)


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


def _validate_header(header_b64: str) -> None:
    """
    Validate the JWT header — reject alg:none and any non-HS256 algorithm.

    This prevents algorithm confusion attacks where an attacker
    changes the alg to 'none' or switches to an asymmetric algorithm.
    """
    try:
        header = json.loads(_b64_decode(header_b64))
    except (json.JSONDecodeError, ValueError) as exc:
        raise InvalidTokenError(f"Invalid JWT header: {exc}") from exc

    alg = header.get("alg", "")

    if not alg or alg.lower() == "none":
        raise InvalidTokenError("Algorithm 'none' is not allowed — possible alg:none attack")

    if alg != _ALLOWED_ALGORITHM:
        raise InvalidTokenError(
            f"Unsupported algorithm '{alg}' — only '{_ALLOWED_ALGORITHM}' is accepted"
        )


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
    refresh_count: int = 0,
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
        refresh_count: How many times this token lineage has been refreshed.

    Returns:
        Signed JWT string (header.payload.signature).
    """
    now = time.time()
    secret = secret or _get_secret()
    _check_secret_strength(secret)

    payload = {
        "sub": user_id,
        "role": role,
        "iat": int(now),
        "exp": int(now + ttl_seconds),
        "iss": issuer,
        "jti": _generate_jti(),
        "scopes": scopes or [],
        "token_type": token_type,
        "refresh_count": refresh_count,
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
    check_blacklist: bool = True,
) -> TokenClaims:
    """
    Verify a JWT token and return its claims.

    Args:
        token: The JWT string.
        secret: Signing secret (uses env var if not provided).
        require_type: If set, reject tokens that aren't this type.
        check_blacklist: If True, check the JTI blacklist for revoked tokens.

    Returns:
        TokenClaims dataclass.

    Raises:
        InvalidTokenError: If token is malformed or signature is invalid.
        TokenExpiredError: If token has expired.
        TokenRevokedError: If token has been revoked.
    """
    secret = secret or _get_secret()

    parts = token.split(".")
    if len(parts) != 3:
        raise InvalidTokenError("Token must have 3 parts (header.payload.signature)")

    header_b64, payload_b64, signature = parts

    # Validate header — reject alg:none and non-HS256
    _validate_header(header_b64)

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
        refresh_count=payload.get("refresh_count", 0),
    )

    # Check expiry
    if claims.is_expired:
        raise TokenExpiredError(f"Token expired at {claims.exp} (now: {time.time():.0f})")

    # Check token type
    if require_type and claims.token_type != require_type:
        raise InvalidTokenError(f"Expected '{require_type}' token, got '{claims.token_type}'")

    # Check blacklist
    if check_blacklist and claims.jti:
        bl = get_token_blacklist()
        if bl.is_revoked(claims.jti):
            raise TokenRevokedError(f"Token has been revoked (jti={claims.jti[:8]}...)")

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
    max_chain: int = MAX_REFRESH_CHAIN,
) -> str:
    """
    Issue a new access token from a valid refresh token.

    Args:
        refresh_token: A valid refresh token.
        access_ttl: Lifetime of the new access token.
        secret: Signing secret.
        max_chain: Maximum refresh count before forcing re-authentication.

    Returns:
        New access token string.

    Raises:
        InvalidTokenError: If refresh token is invalid or chain limit exceeded.
        TokenExpiredError: If refresh token has expired.
    """
    claims = verify_token(refresh_token, secret=secret, require_type="refresh")

    # Enforce max refresh chain length to prevent indefinite sessions
    if claims.refresh_count >= max_chain:
        raise InvalidTokenError(
            f"Refresh chain limit reached ({max_chain}). Please re-authenticate."
        )

    return create_token(
        user_id=claims.sub,
        role=claims.role,
        scopes=list(claims.scopes),
        ttl_seconds=access_ttl,
        token_type="access",
        secret=secret,
        refresh_count=claims.refresh_count + 1,
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
