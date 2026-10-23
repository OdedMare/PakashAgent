"""The one Redis connection a process shares, and what the panel shows of it.

Two things used to live in memory, per process -- the login throttle
(`throttle.py`) and the manager's live signals (`events.py`). With more than
one process each kept its own copy: the throttle allowed N times the
guesses, and a signal raised on one worker never reached a manager streaming
from another. With a Redis URL saved, both hold across processes -- and so
does the model queue (`dal/llm/redis_slots.py`), in priority order, ahead
of its PostgreSQL fallback.

**Redis is an accelerator, never a requirement.** `client()` answers `None`
when no URL is set or the server cannot be reached, and every caller then
does exactly what it did before Redis existed. A caller whose command fails
reports it with `failed()`, which keeps everyone off Redis for a few seconds
instead of each request paying a connect timeout.

**The settings stay live.** The URL (with its host, port and username
overrides), password and prefix are read from the
runtime store on every call; a change closes the old client and the next
call builds a new one. `generation` counts those changes, so a long-lived
user -- the pub/sub listener -- can tell its connection is stale.
"""

import logging
import threading
import time
from typing import Callable
from urllib.parse import urlsplit, urlunsplit

from app.common.runtime_settings.normalizers import redis_connection_url

_log = logging.getLogger("pakash.redis")

# How long to stay off Redis after a failure before trying it again.
RETRY_SECONDS = 5.0
# How often to look for a save another process made to the settings file.
_RELOAD_SECONDS = 3.0
# Fail fast: every caller has an in-memory path that is better than waiting.
_CONNECT_TIMEOUT_SECONDS = 2.0
_SOCKET_TIMEOUT_SECONDS = 5.0


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
    return redis_connection_url(
        settings.redis_url or "",
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
    user = parts.username or ""
    host = parts.hostname or ""
    if parts.port:
        host = "%s:%s" % (host, parts.port)
    netloc = "%s:********@%s" % (user, host)
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
        self._generation = 0
        self._reloaded_at = None

    @property
    def generation(self) -> int:
        with self._lock:
            return self._generation

    def prefix(self) -> str:
        return self._settings().redis_key_prefix or "pakash"

    def key(self, *parts: str) -> str:
        """A key (or channel) under this deployment's prefix."""
        return ":".join((self.prefix(),) + tuple(str(part) for part in parts))

    def client(self):
        """The shared client, or `None` -- not configured, or not reachable."""
        settings = self._settings()
        config = (url_of(settings), settings.redis_password or "")
        with self._lock:
            if config != self._config:
                self._drop()
                self._config = config
                self._down_until = 0.0
                self._error = ""
                self._generation += 1
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
            "prefix": settings.redis_key_prefix or "pakash",
            "error": error,
        }

    def _settings(self):
        """The live settings, re-read from disk now and then so a URL saved
        by another process reaches this one."""
        now = self._clock()
        reload = getattr(self._store, "reload_if_changed", None)
        if reload is not None and (
            self._reloaded_at is None or now - self._reloaded_at >= _RELOAD_SECONDS
        ):
            self._reloaded_at = now
            try:
                reload()
            except Exception:  # noqa: BLE001 -- a bad file keeps the old values
                _log.exception("runtime settings reload failed")
        return self._store.get()

    def _down(self, exc: BaseException) -> None:
        self._down_until = self._clock() + self._retry
        self._error = str(exc) or type(exc).__name__
        _log.warning(
            "redis unavailable, using in-memory state for %.0fs: %s",
            self._retry, self._error,
        )

    def _drop(self) -> None:
        client, self._client = self._client, None
        if client is not None:
            try:
                client.close()
            except Exception:  # noqa: BLE001 -- closing a broken client
                pass


def probe(url: str, password: str = "", prefix: str = "pakash") -> dict:
    """Connect to `url` once and report what is there. Raises on failure.

    Used by the panel to test a connection typed into the form before it is
    saved, and to show what this app keeps in it: who holds the model, who
    is waiting, the accounts locked out, and how many processes listen for
    live signals.
    """
    client = connect(url, password)
    try:
        started = time.perf_counter()
        client.ping()
        latency = (time.perf_counter() - started) * 1000
        info = client.info()
        seconds, micros = client.time()
        now_ms = int(seconds) * 1000 + int(micros) // 1000
        base = prefix or "pakash"
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
                "keys": _count(client, base + ":*"),
                "model_calls": client.zcount(
                    base + ":llm:holders", "(%d" % now_ms, "+inf"
                ),
                "model_waiting": client.zcard(base + ":llm:queue"),
                "locked_accounts": _count(client, base + ":throttle:lock:*"),
                "event_listeners": client.pubsub_numpat(),
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
