"""The pool's checkout check and return reset (`dal/pool_hooks.py`). No database."""

import time

from app.dal import pool_hooks


class _Connection:
    def __init__(self, autocommit=False):
        self.autocommit = autocommit


def test_a_connection_just_returned_skips_the_round_trip(monkeypatch):
    checked = []
    monkeypatch.setattr(pool_hooks.ConnectionPool, "check_connection",
                        staticmethod(checked.append))
    connection = _Connection()
    pool_hooks.reset(connection)

    pool_hooks.check(connection)

    assert checked == []


def test_a_connection_idle_past_the_window_is_still_checked(monkeypatch):
    checked = []
    monkeypatch.setattr(pool_hooks.ConnectionPool, "check_connection",
                        staticmethod(checked.append))
    connection = _Connection()
    pool_hooks.reset(connection)
    connection._pakash_returned_at = time.monotonic() - pool_hooks.FRESH_SECONDS - 1

    pool_hooks.check(connection)

    assert checked == [connection]


def test_a_never_returned_connection_is_checked(monkeypatch):
    checked = []
    monkeypatch.setattr(pool_hooks.ConnectionPool, "check_connection",
                        staticmethod(checked.append))
    connection = _Connection()

    pool_hooks.check(connection)

    assert checked == [connection]


def test_a_returned_connection_leaves_autocommit():
    """A single statement borrows it in autocommit; the next caller must not
    inherit that and find its uncommitted writes already committed."""
    connection = _Connection(autocommit=True)

    pool_hooks.reset(connection)

    assert connection.autocommit is False
