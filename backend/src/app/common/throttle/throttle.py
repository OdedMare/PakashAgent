"""Locking an account out after repeated wrong passwords.

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

In memory and per process. A restart forgets the counts, and with several
workers each keeps its own -- which multiplies the allowance by the worker
count rather than removing it.
"""

import time
from threading import Lock
from typing import Callable, Dict, List, TypeVar

from app.common.errors.errors import AuthError, ForbiddenError, TooManyAttemptsError

T = TypeVar("T")

DEFAULT_LIMIT = 5
DEFAULT_WINDOW_SECONDS = 15 * 60
DEFAULT_LOCKOUT_SECONDS = 15 * 60

# Keys come partly from request bodies (an employee name), so the tables are
# swept once they grow past this rather than being allowed to grow forever.
_SWEEP_ABOVE = 10000

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
    ):
        self._limit = limit
        self._window = window_seconds
        self._lockout = lockout_seconds
        self._clock = clock
        self._failures = {}  # type: Dict[str, List[float]]
        self._locked_until = {}  # type: Dict[str, float]
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
        return result

    def _refuse_if_locked(self, key: str) -> None:
        with self._lock:
            until = self._locked_until.get(key, 0.0)
            remaining = until - self._clock()
            if remaining <= 0:
                self._locked_until.pop(key, None)
                return
        minutes = max(1, int(remaining // 60) + 1)
        raise TooManyAttemptsError(
            "יותר מדי ניסיונות שגויים. נסו שוב בעוד %d דקות." % minutes
        )

    def _record_failure(self, key: str) -> None:
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


__all__ = ["LoginThrottle"]
