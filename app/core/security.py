"""Authentication primitives — password hashing and session tokens.

This module is intentionally self-contained so the authentication strategy can
later be swapped for a managed identity provider (Zitadel, Auth0, Clerk,
Supabase Auth, …) without touching the analytics application. Everything the
rest of the app needs is expressed through the small surface below:

    hash_password / verify_password   — credential storage & checking (bcrypt)
    create_session_token / read_session_token
                                       — stateless, signed session tokens

Session tokens are signed with HMAC-SHA256 using ``settings.jwt_secret_key``.
They are self-describing (user id + expiry) so no server-side session store is
required, yet they cannot be forged or tampered with without the secret.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
import uuid

import bcrypt

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("security")

# A per-process random fallback keeps the app bootable when JWT_SECRET_KEY is
# unset in local dev. Sessions then simply don't survive a restart.
_FALLBACK_SECRET = secrets.token_urlsafe(48)


def _secret() -> bytes:
    key = settings.jwt_secret_key or _FALLBACK_SECRET
    if not settings.jwt_secret_key:
        logger.warning(
            "JWT_SECRET_KEY is not set — using an ephemeral per-process secret. "
            "Set JWT_SECRET_KEY in the environment for persistent sessions."
        )
    return key.encode("utf-8")


# --------------------------------------------------------------------------- #
# Password hashing (bcrypt)
# --------------------------------------------------------------------------- #
def hash_password(password: str) -> str:
    """Return a salted bcrypt hash. Never store the plaintext password."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, password_hash: str | None) -> bool:
    """Constant-time verification of a password against a stored bcrypt hash."""
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        # Malformed/legacy hash — treat as a failed check, never crash.
        return False


# --------------------------------------------------------------------------- #
# Stateless signed session tokens
# --------------------------------------------------------------------------- #
def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64d(data: str) -> bytes:
    pad = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad)


def create_session_token(user_id: uuid.UUID | str, ttl_hours: int | None = None) -> str:
    """Create a signed ``<payload>.<signature>`` session token."""
    ttl = (ttl_hours if ttl_hours is not None else settings.session_ttl_hours) * 3600
    payload = {
        "sub": str(user_id),
        "iat": int(time.time()),
        "exp": int(time.time()) + ttl,
    }
    body = _b64e(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    sig = _b64e(hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).digest())
    return f"{body}.{sig}"


def read_session_token(token: str | None) -> uuid.UUID | None:
    """Validate a session token and return the user id, or ``None`` if invalid.

    Rejects tampered signatures and expired tokens.
    """
    if not token or "." not in token:
        return None
    body, _, sig = token.partition(".")
    expected = _b64e(hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        payload = json.loads(_b64d(body))
        if int(payload["exp"]) < int(time.time()):
            return None
        return uuid.UUID(str(payload["sub"]))
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None
