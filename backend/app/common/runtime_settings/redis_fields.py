"""The Redis connection fields: how each is read, from env and from a save.

Kept beside the store rather than in it, so the store keeps one job. The
same functions normalize an env value at start-up (where a bad one falls
back instead of failing the boot) and a panel save (where it is refused).
"""

import re
from typing import Optional
from urllib.parse import quote, urlsplit, urlunsplit

_SCHEMES = ("redis://", "rediss://", "unix://")
_PREFIX_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")
_HOST_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,253}$")
DEFAULT_PREFIX = "pakash"
DEFAULT_PORT = 6379
# A cached read past a day old is no longer a cache of anything.
_MAX_TTL_SECONDS = 86400

FIELDS = (
    "redis_url", "redis_host", "redis_port", "redis_username",
    "redis_password", "redis_key_prefix", "redis_cache_ttl_seconds",
)


def normalize_url(value: str) -> str:
    """A Redis URL, or "" for "no Redis". A bare `host:port` -- what people
    type when they know where Redis runs -- is read as `redis://host:port`."""
    cleaned = (value or "").strip()
    if not cleaned:
        return ""
    if "://" not in cleaned:
        cleaned = "redis://" + cleaned
    if not cleaned.lower().startswith(_SCHEMES):
        raise ValueError("redis_url must start with redis://, rediss:// or unix://")
    return cleaned


def normalize_host(value: str) -> str:
    """A bare host name or address, or "" for "take it from the URL". An
    IPv6 address may come with or without its brackets."""
    cleaned = (value or "").strip().strip("[]")
    if not cleaned:
        return ""
    if not _HOST_RE.match(cleaned):
        raise ValueError("redis_host must be a host name or address only")
    return cleaned


def normalize_port(value) -> Optional[int]:
    """1-65535, or None for "take it from the URL"."""
    if value is None or str(value).strip() == "":
        return None
    port = int(value)
    if not 1 <= port <= 65535:
        raise ValueError("redis_port must be between 1 and 65535")
    return port


def normalize_prefix(value: str) -> str:
    """The key prefix every key this app writes starts with. A space or a
    glob character would make the SCAN that counts our keys match someone
    else's, so it is kept to a plain token."""
    cleaned = (value or "").strip().rstrip(":")
    if not cleaned:
        return DEFAULT_PREFIX
    if not _PREFIX_RE.match(cleaned):
        raise ValueError("redis_key_prefix may hold letters, digits and _ . : - only")
    return cleaned


def normalize_ttl(value) -> int:
    """Seconds a cached read may live; 0 turns the cache off."""
    return min(_MAX_TTL_SECONDS, max(0, int(value)))


def connection_url(
    url: str, host: str = "", port: Optional[int] = None, username: str = "",
) -> str:
    """The URL a client connects to: `url` with the explicit host, port and
    username written over its own -- the same contract as the database
    fields. With no URL, a host alone is enough (`redis://host:6379`). ""
    means no Redis. A `unix://` socket has no host or port to override.

    The password is not folded in: it travels beside the URL as AUTH, so a
    URL that is shown or logged never carries one it did not already have.
    """
    url = (url or "").strip()
    if not url and not host:
        return ""
    if not url:
        url = "redis://localhost"
    if url.lower().startswith("unix://") or not (host or port or username):
        return url
    parts = urlsplit(url)
    name = host or parts.hostname or "localhost"
    if ":" in name:
        name = "[%s]" % name
    netloc = "%s:%d" % (name, port or parts.port or DEFAULT_PORT)
    user = quote(username, safe="") if username else (parts.username or "")
    if parts.password is not None:
        user = "%s:%s" % (user, parts.password)
    if user:
        netloc = "%s@%s" % (user, netloc)
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, ""))


_NORMALIZERS = {
    "redis_url": normalize_url,
    "redis_host": normalize_host,
    "redis_port": normalize_port,
    "redis_username": lambda value: str(value).strip(),
    "redis_key_prefix": normalize_prefix,
    "redis_cache_ttl_seconds": normalize_ttl,
}

# Fallbacks for an env value that does not normalize: no Redis rather than
# a failed start-up.
_FALLBACKS = {
    "redis_url": "", "redis_host": "", "redis_port": None,
    "redis_username": "", "redis_key_prefix": DEFAULT_PREFIX,
    "redis_cache_ttl_seconds": 300,
}


def normalized(key: str, value):
    """One saved field's stored value. Raises on an unusable one."""
    normalize = _NORMALIZERS.get(key)
    return normalize(value) if normalize else value


def from_env(env) -> dict:
    """Every Redis field from the environment, never failing the boot."""
    values = {"redis_password": env.redis_password or ""}
    for key, fallback in _FALLBACKS.items():
        try:
            values[key] = _NORMALIZERS[key](getattr(env, key))
        except (TypeError, ValueError):
            values[key] = fallback
    return values
