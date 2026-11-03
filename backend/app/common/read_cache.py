"""Heavy board reads kept in Redis until the team's data changes (D50).

The overview, the stats panel and the board's periods are each several
queries and a full audit. They are read far more often than they change --
every tab switch, every poll, every member opening the share link -- so a
copy is kept in Redis and PostgreSQL is asked again only after a write.

**Versions, not deletes.** Each team has a generation counter, and the
deployment one more. A cached read's key carries both, so a write retires
everything its team had cached by one `INCR`, with no key to find and
delete. A read that started before the write and finishes after it lands
under the old generation, where nobody will ask for it again.

**What counts as a write** is noticed at the cursor (`dal/write_marks.py`)
and told here after the commit -- from the API and from the worker alike,
since every process shares the same Redis. A write with no team in context
(the operator console, a commander's duties) bumps the deployment's counter.

**Never wrong for long, never required.** No Redis, a cache TTL of 0, or a
command that fails: the read goes to PostgreSQL as it always did. A write
that could not reach Redis leaves a debt, paid by bumping the deployment's
counter the next time Redis answers; the TTL bounds anything else.

Every key starts with the configured prefix (`RedisHub.key`).
"""

import hashlib
import json
import logging
import time
from typing import Any, Callable, Iterable

from fastapi.encoders import jsonable_encoder

from app.common.time_context import israel_today

_log = logging.getLogger("pakash.cache")

# A generation counter outlives every read cached under it (the TTL is
# capped at a day); one that is evicted anyway restarts from the clock
# (`_seed`), so it can never revive an old read.
_GENERATION_TTL_SECONDS = 2 * 86400
_GLOBAL = ""


class ReadCache:
    def __init__(self, hub, store, today: Callable[[], Any] = israel_today):
        self._hub = hub
        self._store = store
        self._today = today
        # A fresh process may have missed writes while it had no Redis.
        self._owed = True

    def read(self, team_id: str, name: str, args: tuple, load: Callable[[], Any]):
        """`load()`'s answer, JSON-ready -- from Redis when it is current."""
        ttl = self._ttl()
        client = self._hub.client() if ttl else None
        if client is None:
            return jsonable_encoder(load())
        try:
            self._settle(client)
            key = self._key(client, team_id, name, args)
            cached = client.get(key)
        except Exception as exc:  # noqa: BLE001 -- any failure means PostgreSQL
            self._hub.failed(exc)
            return jsonable_encoder(load())
        if cached is not None:
            return json.loads(cached)
        value = jsonable_encoder(load())
        try:
            client.set(key, json.dumps(value, ensure_ascii=False), ex=ttl)
        except Exception as exc:  # noqa: BLE001
            self._hub.failed(exc)
        return value

    def written(self, teams: Iterable[str]) -> None:
        """Retire every cached read of `teams` (`""`: of every team)."""
        teams = set(teams)
        if not teams:
            return
        client = self._hub.client()
        if client is None:
            self._owed = True
            return
        try:
            if _GLOBAL in teams:
                teams = {_GLOBAL}
            _bump(client, [self._generation_key(team) for team in teams])
        except Exception as exc:  # noqa: BLE001
            self._owed = True
            self._hub.failed(exc)

    def _settle(self, client) -> None:
        """Pay a missed invalidation before trusting anything cached."""
        if not self._owed:
            return
        _bump(client, [self._generation_key(_GLOBAL)])
        self._owed = False

    def _key(self, client, team_id: str, name: str, args: tuple) -> str:
        deployment, team = _generations(
            client, [self._generation_key(_GLOBAL), self._generation_key(team_id)],
        )
        # Today is part of every key: the overview names it, and the audit
        # and the views read what is past and what is ahead from it.
        digest = hashlib.sha256(json.dumps(
            [list(args), str(self._today())], default=str, ensure_ascii=False,
        ).encode("utf-8")).hexdigest()[:32]
        return self._hub.key(
            "cache", "read", team_id, "%s.%s" % (deployment, team), name, digest,
        )

    def _generation_key(self, team_id: str) -> str:
        if team_id == _GLOBAL:
            return self._hub.key("cache", "generation")
        return self._hub.key("cache", "team", team_id, "generation")

    def _ttl(self) -> int:
        try:
            return int(getattr(self._store.get(), "redis_cache_ttl_seconds", 0) or 0)
        except (TypeError, ValueError):
            return 0


def _seed() -> int:
    """Where a counter starts: the clock, in nanoseconds. A counter Redis
    evicted or let expire starts again above every value it ever held, so
    an old read can never match a new generation."""
    return time.time_ns()


def _generations(client, counters) -> list:
    pipe = client.pipeline(transaction=False)
    for counter in counters:
        pipe.set(counter, _seed(), nx=True, ex=_GENERATION_TTL_SECONDS)
        pipe.get(counter)
    return pipe.execute()[1::2]


def _bump(client, counters) -> None:
    pipe = client.pipeline(transaction=False)
    for counter in counters:
        pipe.set(counter, _seed(), nx=True)
        pipe.incr(counter)
        pipe.expire(counter, _GENERATION_TTL_SECONDS)
    pipe.execute()


class NoCache:
    """The cache's shape with nothing behind it, for tests and wiring."""

    def read(self, team_id, name, args, load):
        return jsonable_encoder(load())

    def written(self, teams) -> None:
        pass
