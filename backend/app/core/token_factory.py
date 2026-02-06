"""Pure functions for creating and decoding JWT service tokens.

No classes, no state — just encode/decode. Used by the auth dependency and
by management scripts that generate tokens for the agent or admin use.
"""

import hashlib
import hmac
import base64
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


@dataclass(frozen=True)
class TokenPayload:
    """Decoded JWT payload. Immutable."""
    sub: str
    role: str
    exp: datetime


def create_token(
    subject: str,
    role: str,
    secret: str,
    algorithm: str = "HS256",
    expires_hours: int = 24,
) -> str:
    """Create a signed JWT token.

    Args:
        subject: Token subject (e.g. ``"agent"`` or ``"admin"``).
        role: Role claim (e.g. ``"service"`` or ``"admin"``).
        secret: HMAC signing key.
        algorithm: Only HS256 supported.
        expires_hours: Hours until expiry.

    Returns:
        Encoded JWT string.
    """
    if algorithm != "HS256":
        raise ValueError(f"Unsupported algorithm: {algorithm}")

    now = time.time()
    payload = {
        "sub": subject,
        "role": role,
        "iat": int(now),
        "exp": int(now + expires_hours * 3600),
        "iss": "isocrates",
    }

    header = {"alg": "HS256", "typ": "JWT"}
    segments = [
        _b64encode(json.dumps(header).encode()),
        _b64encode(json.dumps(payload).encode()),
    ]
    signing_input = b".".join(segments)
    signature = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
    segments.append(_b64encode(signature))
    return b".".join(segments).decode()


def decode_token(token: str, secret: str, algorithm: str = "HS256") -> Optional[TokenPayload]:
    """Decode and validate a JWT token.

    Returns ``None`` on any validation failure (bad signature, expired, malformed)
    rather than raising — callers decide what to do with absence.

    Args:
        token: Encoded JWT string.
        secret: HMAC signing key.
        algorithm: Only HS256 supported.

    Returns:
        ``TokenPayload`` if valid, ``None`` otherwise.
    """
    try:
        parts = token.encode().split(b".")
        if len(parts) != 3:
            return None

        signing_input = parts[0] + b"." + parts[1]
        expected_sig = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
        actual_sig = _b64decode(parts[2])

        if not hmac.compare_digest(expected_sig, actual_sig):
            return None

        payload = json.loads(_b64decode(parts[1]))

        exp = payload.get("exp", 0)
        if time.time() > exp:
            return None

        return TokenPayload(
            sub=payload.get("sub", ""),
            role=payload.get("role", ""),
            exp=datetime.fromtimestamp(exp, tz=timezone.utc),
        )
    except (json.JSONDecodeError, KeyError, ValueError, IndexError):
        return None


# --- base64url helpers (no padding, URL-safe) ---

def _b64encode(data: bytes) -> bytes:
    return base64.urlsafe_b64encode(data).rstrip(b"=")


def _b64decode(data: bytes) -> bytes:
    padding = 4 - len(data) % 4
    if padding != 4:
        data += b"=" * padding
    return base64.urlsafe_b64decode(data)
