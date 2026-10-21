"""The model concurrency limit, held in Redis across every process.

The same contract as `PostgresModelSlots`, which it replaces whenever Redis
is reachable:

- **one limit for the deployment** -- the API workers and `app.worker` wait
  in one line, sized by `llm_max_concurrency` as saved right now, so a
  change in the panel applies to the next call;
- **one call in flight per team** -- the fairness quota: a team's second
  call waits for its first, without holding back other teams behind it.

And one promise the advisory locks could not keep: **order**. Tickets are
served by priority, then arrival, so a manager's chat goes ahead of a
queued build day and nobody is overtaken by a luckier poll.

**A process that dies gives its place back.** A holder renews a short lease
while its call runs, and a waiter refreshes its ticket every poll; whatever
is not renewed is swept by the next caller. Times come from the Redis
server's clock, so hosts whose clocks drift still agree.

**Redis is never required.** Not configured, unreachable when a call starts,
or failing while it waits -- the call goes to `fallback` instead (the
PostgreSQL slots, or the process-local ones without a database).
"""

import logging
import threading
import time
import uuid
from contextlib import contextmanager
from typing import Callable, Optional

from app.common.activity import report_activity
from app.dal.llm.model_slots import INTERACTIVE, ModelBusy
from app.dal.llm.team_context import current_team

_log = logging.getLogger("pakash.llm.slots")

# A holder renews its lease every third of this. Long enough to ride out a
# GC pause or a slow round-trip, short enough that a dead process frees its
# slot quickly.
LEASE_SECONDS = 30.0
# How long a waiter's ticket survives without being refreshed.
WAIT_TTL_SECONDS = 10.0
# How often a waiter asks again. A model call takes seconds; a twentieth of
# one spent noticing a free slot is noise.
POLL_SECONDS = 0.05
# Priority dominates arrival: a ticket's score is priority * this + sequence.
_PRIORITY_STRIDE = 10 ** 13
# What `PostgresModelSlots` calls a call with no team: they share one quota.
_UNSCOPED = "unscoped"

# KEYS: queue, alive, holders, teams.
# ARGV: ticket, score, team, wait_ttl_ms, lease_ms, limit.
# Walks the queue in order, giving each waiter whose team holds nothing a
# free slot, until the slots run out or our ticket is reached.
_ACQUIRE = """
local t = redis.call('TIME')
local now = tonumber(t[1]) * 1000 + math.floor(tonumber(t[2]) / 1000)
for _, gone in ipairs(redis.call('ZRANGEBYSCORE', KEYS[3], '-inf', now)) do
  redis.call('ZREM', KEYS[3], gone)
  redis.call('HDEL', KEYS[4], gone)
end
for _, gone in ipairs(redis.call('ZRANGEBYSCORE', KEYS[2], '-inf', now)) do
  redis.call('ZREM', KEYS[1], gone)
  redis.call('ZREM', KEYS[2], gone)
  redis.call('HDEL', KEYS[4], gone)
end
redis.call('ZADD', KEYS[1], 'NX', ARGV[2], ARGV[1])
redis.call('ZADD', KEYS[2], now + tonumber(ARGV[4]), ARGV[1])
redis.call('HSET', KEYS[4], ARGV[1], ARGV[3])
local free = tonumber(ARGV[6]) - redis.call('ZCARD', KEYS[3])
if free <= 0 then return 0 end
local busy = {}
for _, holder in ipairs(redis.call('ZRANGE', KEYS[3], 0, -1)) do
  local team = redis.call('HGET', KEYS[4], holder)
  if team then busy[team] = true end
end
for _, waiter in ipairs(redis.call('ZRANGE', KEYS[1], 0, -1)) do
  local team = redis.call('HGET', KEYS[4], waiter) or ''
  if not busy[team] then
    if waiter == ARGV[1] then
      redis.call('ZREM', KEYS[1], waiter)
      redis.call('ZREM', KEYS[2], waiter)
      redis.call('ZADD', KEYS[3], now + tonumber(ARGV[5]), waiter)
      return 1
    end
    busy[team] = true
    free = free - 1
    if free <= 0 then return 0 end
  end
end
return 0
"""

# KEYS: holders. ARGV: ticket, lease_ms. Renews only a lease still held.
_RENEW = """
local t = redis.call('TIME')
local now = tonumber(t[1]) * 1000 + math.floor(tonumber(t[2]) / 1000)
return redis.call('ZADD', KEYS[1], 'XX', 'CH', now + tonumber(ARGV[2]), ARGV[1])
"""


# A Redis hash tag: a sharded server (Redis Cluster, Redis Enterprise) puts
# keys by the text between the braces, so every key the scripts touch lands
# in one slot. Without it a script over four keys fails with CROSSSLOT.
SLOT_TAG = "{llm}"


def slot_keys(redis) -> tuple:
    """queue, alive, holders, teams -- also read by the panel's probe."""
    return tuple(
        redis.key(SLOT_TAG, name)
        for name in ("queue", "alive", "holders", "teams")
    )


class _Held:
    """One slot held in Redis, and the thread keeping its lease alive."""

    def __init__(self, client, keys, ticket, lease_ms):
        self._client, self._keys, self._ticket = client, keys, ticket
        self._lease_ms = lease_ms
        self._stop = threading.Event()
        threading.Thread(
            target=self._renew, name="model-slot-lease", daemon=True,
        ).start()

    def _renew(self) -> None:
        while not self._stop.wait(self._lease_ms / 3000.0):
            try:
                self._client.eval(
                    _RENEW, 1, self._keys[2], self._ticket, self._lease_ms,
                )
            except Exception as exc:  # noqa: BLE001 -- the call itself goes on
                _log.warning("model slot lease renewal failed: %s", exc)

    def release(self) -> None:
        self._stop.set()
        try:
            pipe = self._client.pipeline()
            pipe.zrem(self._keys[2], self._ticket)
            pipe.hdel(self._keys[3], self._ticket)
            pipe.execute()
        except Exception as exc:  # noqa: BLE001 -- the lease expires anyway
            _log.warning("model slot release failed, lease will expire: %s", exc)


class RedisModelSlots:
    def __init__(
        self, store, redis, fallback: Callable[[], object],
        lease_seconds: float = LEASE_SECONDS,
        poll_seconds: float = POLL_SECONDS,
        wait_ttl_seconds: float = WAIT_TTL_SECONDS,
    ) -> None:
        self._store = store
        self._redis = redis
        self._fallback = fallback
        self._lease_ms = int(lease_seconds * 1000)
        self._wait_ms = int(wait_ttl_seconds * 1000)
        self._poll = poll_seconds

    @contextmanager
    def reserve(
        self, priority: int = INTERACTIVE, timeout: Optional[float] = None,
    ):
        deadline = None if timeout is None else time.monotonic() + timeout
        held = self._try_shared(priority, deadline)
        if held is None:
            remaining = None if deadline is None else deadline - time.monotonic()
            if remaining is not None and remaining <= 0:
                raise ModelBusy
            with self._fallback().reserve(priority, remaining):
                yield
            return
        try:
            report_activity("המודל מכין תשובה…")
            yield
            report_activity("בודק את התוצאה…")
        finally:
            held.release()

    def _try_shared(self, priority: int, deadline) -> Optional[_Held]:
        """A slot from Redis, or `None` to use the fallback instead."""
        client = self._redis.client()
        if client is None:
            return None
        report_activity("ממתין למודל…")
        try:
            return self._acquire(client, priority, deadline)
        except ModelBusy:
            raise
        except Exception as exc:  # noqa: BLE001 -- the fallback takes over
            _log.warning("redis model slots unavailable: %s", exc)
            self._redis.failed(exc)
            return None

    def _acquire(self, client, priority: int, deadline) -> _Held:
        keys = slot_keys(self._redis)
        ticket = uuid.uuid4().hex
        team = current_team() or _UNSCOPED
        score = priority * _PRIORITY_STRIDE + client.incr(
            self._redis.key(SLOT_TAG, "seq")
        )
        try:
            while True:
                if client.eval(
                    _ACQUIRE, 4, *keys, ticket, score, team, self._wait_ms,
                    self._lease_ms, self._limit(),
                ):
                    return _Held(client, keys, ticket, self._lease_ms)
                if deadline is not None and time.monotonic() >= deadline:
                    raise ModelBusy
                time.sleep(self._poll)
        except BaseException:
            _leave(client, keys, ticket)
            raise

    def _limit(self) -> int:
        """Read on every poll, like the PostgreSQL slots: a limit saved in
        the panel applies to the next call."""
        try:
            return max(1, int(getattr(
                self._store.get(), "llm_max_concurrency", 1
            ) or 1))
        except (TypeError, ValueError):
            return 1


def _leave(client, keys, ticket) -> None:
    try:
        pipe = client.pipeline()
        pipe.zrem(keys[0], ticket)
        pipe.zrem(keys[1], ticket)
        pipe.hdel(keys[3], ticket)
        pipe.execute()
    except Exception:  # noqa: BLE001 -- the ticket expires unrefreshed
        pass


__all__ = ["RedisModelSlots", "SLOT_TAG", "slot_keys"]
