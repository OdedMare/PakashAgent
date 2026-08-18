"""Signed workspace session cookies.

The cookie carries the team id and a role, signed with HMAC-SHA256 so the
browser can hold it without being able to edit it. There is no server-side
session table on purpose: the only thing a session needs to say is "this
browser proved it knows team X's password", which fits in the cookie itself,
and a table would need expiry sweeping to earn its keep.

What this is not: it is not a JWT and does not try to be. No algorithm field
(so no `alg: none` to get wrong), no library, and a format this file fully
controls.
"""

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Optional

# Role names as they travel in the cookie. The member role is issued by the
# share link and never by a password, which is what keeps D5 -- employees are
# read-only -- enforceable at the routing layer rather than by convention.
ROLE_BOSS = "boss"
ROLE_MEMBER = "member"

COOKIE_NAME = "pakash_session"


def _b64(raw: bytes) -> str:
    """URL-safe base64 without padding -- `=` is legal in a cookie value but
    routinely mangled by proxies that treat it as a key/value separator."""
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _unb64(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def issue(secret: str, team_id: str, role: str, days: int) -> str:
    """`<payload>.<signature>`, both URL-safe base64."""
    payload = {
        "team_id": team_id,
        "role": role,
        "exp": int(time.time()) + days * 86400,
    }
    body = _b64(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    return "%s.%s" % (body, _sign(secret, body))


def read(secret: str, cookie: Optional[str]) -> Optional[dict]:
    """The payload if the cookie is authentic and unexpired, else None.

    Every failure -- missing, malformed, forged, expired -- returns None
    rather than raising. The caller's job is the same in all four cases (send
    the visitor to the login screen), and distinguishing them in an error
    message would only tell an attacker which half they got right.
    """
    if not cookie or "." not in cookie:
        return None
    body, _, signature = cookie.rpartition(".")
    # Compared in constant time: a byte-at-a-time comparison leaks how much of
    # a forged signature was correct, which is enough to construct one.
    if not hmac.compare_digest(_sign(secret, body), signature):
        return None
    try:
        payload = json.loads(_unb64(body).decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    if int(payload.get("exp", 0)) < time.time():
        return None
    if payload.get("role") not in (ROLE_BOSS, ROLE_MEMBER):
        return None
    if not payload.get("team_id"):
        return None
    return payload


def _sign(secret: str, body: str) -> str:
    return _b64(hmac.new(
        secret.encode("utf-8"), body.encode("utf-8"), hashlib.sha256
    ).digest())


def generate_secret() -> str:
    return secrets.token_urlsafe(32)


__all__ = [
    "COOKIE_NAME", "ROLE_BOSS", "ROLE_MEMBER",
    "issue", "read", "generate_secret",
]
