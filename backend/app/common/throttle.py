"""Account lockout after repeated wrong passwords.

Every credential in this app is short enough to guess by brute force when
nothing stops the guessing: an employee passcode is a handful of digits, and
the settings password is six. So each check that compares a secret runs
through `attempt()`, which counts failures per account and refuses the
account for a while once there are too many.

Keyed by *account*, not by IP. Behind the Next.js proxy every request
arrives from the frontend container, so an IP key would lock out the whole
workplace at once; and a client-supplied `X-Forwarded-For` is whatever the
attacker chooses. The cost of an account key is that someone can lock a
real user out for `lockout_seconds` by guessing badly on purpose -- an
annoyance, where the alternative is a guessable passcode.

Shared through PostgreSQL when handed the repository
(`dal/repository/throttle.py`): the counts and the lockouts then hold for
every process and survive a restart. Without one -- tests, small adapters --
each process keeps its own in memory. A database that stops answering
mid-way drops the check back to memory rather than refusing logins.

The shared window is fixed rather than sliding: it opens with the first
wrong guess and closes `window_seconds` later. Five guesses inside it lock
the account either way.
"""

import logging
import time
from threading import Lock
from typing import Callable, Optional, TypeVar

from app.common.errors import AuthError, ForbiddenError, TooManyAttemptsError

T = TypeVar("T")

DEFAULT_LIMIT = 5
DEFAULT_WINDOW_SECONDS = 15 * 60
DEFAULT_LOCKOUT_SECONDS = 15 * 60

# Keys come partly from request bodies (an employee name), so the tables are
# swept once they grow past this rather than being allowed to grow forever.
_SWEEP_ABOVE = 10000

_log = logging.getLogger("pakash.throttle")

# What counts as a wrong secret. Anything else -- a database error, say --
# is not the caller's guess failing and must not count against them.
_REFUSALS = (AuthError, ForbiddenError)


class LoginThrottle:
    def __init__(
        self,
        limit: int = DEFAULT_LIMIT,
        window_seconds: float = DEFAULT_WINDOW_SECONDS,
        lockout_seconds: float = DEFAULT_LOCKOUT_SECONDS,
        clock: Callable[[], float] = time.monotonic,
        shared=None,
    ):
        # The repository (`throttle_locked_for`, `throttle_fail`,
        # `throttle_clear`), or None for memory only.
        self._store = shared
        self._limit = limit
        self._window = window_seconds
        self._lockout = lockout_seconds
        self._clock = clock
        self._failures: dict[str, list[float]] = {}
        self._locked_until: dict[str, float] = {}
        self._lock = Lock()

    def attempt(self, key: str, check: Callable[[], T]) -> T:
        """Run `check` unless `key` is locked; count it if it refuses.

        A success clears the account's count, so a user who mistypes twice
        and then gets it right starts fresh.
        """
        self._refuse_if_locked(key)
        try:
            result = check()
        except _REFUSALS:
            self._record_failure(key)
            raise
        with self._lock:
            self._failures.pop(key, None)
        self._shared(lambda store: store.throttle_clear(key))
        return result

    def _refuse_if_locked(self, key: str) -> None:
        remaining = self._shared(lambda store: store.throttle_locked_for(key))
        if remaining is None:
            remaining = self._local_remaining(key)
        if remaining <= 0:
            return
        minutes = max(1, int(remaining // 60) + 1)
        raise TooManyAttemptsError(
            "יותר מדי ניסיונות שגויים. נסו שוב בעוד %d דקות." % minutes
        )

    def _local_remaining(self, key: str) -> float:
        with self._lock:
            until = self._locked_until.get(key, 0.0)
            remaining = until - self._clock()
            if remaining <= 0:
                self._locked_until.pop(key, None)
            return remaining

    def _record_failure(self, key: str) -> None:
        if self._shared(lambda store: store.throttle_fail(
                key, self._limit, self._window, self._lockout) or True):
            return
        with self._lock:
            now = self._clock()
            recent = [
                at for at in self._failures.get(key, []) if now - at < self._window
            ]
            recent.append(now)
            if len(recent) >= self._limit:
                self._locked_until[key] = now + self._lockout
                self._failures.pop(key, None)
            else:
                self._failures[key] = recent
            if len(self._failures) + len(self._locked_until) > _SWEEP_ABOVE:
                self._sweep(now)

    def _sweep(self, now: float) -> None:
        self._failures = {
            key: times for key, times in self._failures.items()
            if times and now - times[-1] < self._window
        }
        self._locked_until = {
            key: until for key, until in self._locked_until.items() if until > now
        }

    def _shared(self, command) -> Optional[object]:
        """Run `command` on the shared store. `None` means "use memory": no
        store, or it failed just now."""
        if self._store is None:
            return None
        try:
            return command(self._store)
        except Exception as exc:  # noqa: BLE001 -- memory is the fallback
            _log.warning("throttle falling back to memory: %s", exc)
            return None
