"""The one Redis connection a process shares, and what the panel shows of it.

Redis carries the read cache (`common/read_cache.py`, D50) and nothing
else: PostgreSQL stays the only source of truth (D35), and every key here is
a copy that may be thrown away at any moment.

**Redis is an accelerator, never a requirement.** `client()` answers `None`
when no URL is set or the server cannot be reached, and every caller then
reads PostgreSQL exactly as it did before Redis existed. A caller whose
command fails reports it with `failed()`, which keeps everyone off Redis for
a few seconds instead of each request paying a connect timeout.

**The settings stay live.** The URL (with its host, port and username
overrides), password and prefix are read from the runtime store on every
call; a change closes the old client and the next call builds a new one.

**Every key starts with the configured prefix** (`key()`), so one Redis can
serve several deployments, or other applications, without their keys
meeting -- and the panel can count exactly this app's keys.
"""

import logging
import threading
import time
from typing import Callable
from urllib.parse import urlsplit, urlunsplit

from app.common.runtime_settings.redis_fields import (
    DEFAULT_PREFIX,
    connection_url,
)

_log = logging.getLogger("pakash.redis")

# How long to stay off Redis after a failure before trying it again.
RETRY_SECONDS = 5.0
# Fail fast: every caller has a PostgreSQL path that is better than waiting.
_CONNECT_TIMEOUT_SECONDS = 2.0
_SOCKET_TIMEOUT_SECONDS = 2.0


def connect(url: str, password: str = ""):
    """A client for `url`. Imported here so a missing package is reported as
    "Redis unavailable" by whoever asked, not as a failed start-up."""
    import redis

    return redis.Redis.from_url(
        url,
        password=password or None,
        decode_responses=True,
        socket_connect_timeout=_CONNECT_TIMEOUT_SECONDS,
        socket_timeout=_SOCKET_TIMEOUT_SECONDS,
        health_check_interval=30,
    )


def url_of(settings) -> str:
    """The URL `settings` connect to: `redis_url` with the explicit host,
    port and username written over it. "" means no Redis."""
    return connection_url(
        getattr(settings, "redis_url", "") or "",
        getattr(settings, "redis_host", "") or "",
        getattr(settings, "redis_port", None),
        getattr(settings, "redis_username", "") or "",
    )


def mask_url(url: str) -> str:
    """The URL with any password in it replaced, fit to show or log."""
    if not url:
        return ""
    try:
        parts = urlsplit(url)
    except ValueError:
        return "redis://…"
    if parts.password is None:
        return url
    host = parts.hostname or ""
    if parts.port:
        host = "%s:%s" % (host, parts.port)
    netloc = "%s:********@%s" % (parts.username or "", host)
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, ""))


class RedisHub:
    def __init__(
        self, store, factory: Callable = connect,
        retry_seconds: float = RETRY_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._store = store
        self._factory = factory
        self._retry = retry_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._config = None
        self._client = None
        self._down_until = 0.0
        self._error = ""

    def _settings(self):
        """The settings as held, never polled: `client()` runs inside a
        write's invalidation, where a database read would be a second
        connection taken while telling about the first (`store.get()` polls
        the shared settings). Every request's own `get()` keeps them fresh."""
        return getattr(self._store, "peek", self._store.get)()

    def prefix(self) -> str:
        return getattr(self._settings(), "redis_key_prefix", "") or DEFAULT_PREFIX

    def key(self, *parts) -> str:
        """A key under this deployment's prefix."""
        return ":".join((self.prefix(),) + tuple(str(part) for part in parts))

    def client(self):
        """The shared client, or `None` -- not configured, or not reachable."""
        settings = self._settings()
        config = (url_of(settings), getattr(settings, "redis_password", "") or "")
        with self._lock:
            if config != self._config:
                self._drop()
                self._config = config
                self._down_until = 0.0
                self._error = ""
            if not config[0]:
                return None
            if self._client is not None:
                return self._client
            if self._clock() < self._down_until:
                return None
            try:
                client = self._factory(*config)
                client.ping()
            except Exception as exc:  # noqa: BLE001 -- any failure means "not now"
                self._down(exc)
                return None
            _log.info("redis connected url=%s", mask_url(config[0]))
            self._client = client
            self._error = ""
            return client

    def failed(self, exc: BaseException) -> None:
        """A command on the shared client failed: stay off Redis a while."""
        with self._lock:
            self._drop()
            self._down(exc)

    def status(self) -> dict:
        """What this process is using right now, for the panel."""
        client = self.client()
        settings = self._settings()
        with self._lock:
            error = self._error
        return {
            "configured": bool(url_of(settings)),
            "connected": client is not None,
            "url": mask_url(url_of(settings)),
            "prefix": self.prefix(),
            "error": error,
        }

    def _down(self, exc: BaseException) -> None:
        self._down_until = self._clock() + self._retry
        self._error = str(exc) or type(exc).__name__
        _log.warning(
            "redis unavailable, reading PostgreSQL for %.0fs: %s",
            self._retry, self._error,
        )

    def _drop(self) -> None:
        client, self._client = self._client, None
        if client is not None:
            try:
                client.close()
            except Exception:  # noqa: BLE001 -- closing a broken client
                pass


def probe(url: str, password: str = "", prefix: str = DEFAULT_PREFIX) -> dict:
    """Connect to `url` once and report what is there. Raises on failure.

    Used by the panel to test a connection typed into the form before it is
    saved, and to show what this app keeps in it under `prefix`.
    """
    client = connect(url, password)
    try:
        started = time.perf_counter()
        client.ping()
        latency = (time.perf_counter() - started) * 1000
        info = client.info()
        base = prefix or DEFAULT_PREFIX
        return {
            "server": {
                "version": info.get("redis_version", ""),
                "mode": info.get("redis_mode", ""),
                "uptime_seconds": info.get("uptime_in_seconds", 0),
                "used_memory": info.get("used_memory_human", ""),
                "connected_clients": info.get("connected_clients", 0),
                "keys": client.dbsize(),
                "latency_ms": round(latency, 1),
            },
            "app": {
                "prefix": base,
                "keys": _count(client, base + ":*"),
                "cached_reads": _count(client, base + ":cache:read:*"),
            },
        }
    finally:
        client.close()


def _count(client, pattern: str, ceiling: int = 10000) -> int:
    """Keys matching `pattern`, by SCAN -- never KEYS, which blocks the
    server -- and capped, since this is a number on a screen."""
    total = 0
    for _ in client.scan_iter(match=pattern, count=500):
        total += 1
        if total >= ceiling:
            break
    return total
