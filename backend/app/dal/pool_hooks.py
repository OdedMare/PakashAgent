"""What the pool does to a connection on the way out and on the way back.

**The health check is skipped for a connection that was just returned.**
`ConnectionPool.check_connection` is a full round trip, and the pool runs it
on every checkout. A busy process hands the same connection out again within
milliseconds of getting it back, and a connection that was fine a moment ago
is almost certainly fine now; paying a network round trip to learn that, on
every query, is what made a page load wait on the pool. A connection idle
longer than `FRESH_SECONDS` is still checked, so one left behind by a
database restart is noticed and replaced before anyone queries on it.

**A returned connection is reset to `autocommit = False`.** A single
statement borrows one in autocommit (`database.single_statement`) and the
pool never resets that attribute itself, so the next caller -- one that
expects `commit()` to mean something -- would otherwise get a connection that
commits behind its back.
"""

import time

from psycopg_pool import ConnectionPool

# A connection returned this recently skips the checkout round trip.
FRESH_SECONDS = 2.0
_RETURNED_AT = "_pakash_returned_at"


def check(connection) -> None:
    """Check only a connection that has been idle a while."""
    returned = getattr(connection, _RETURNED_AT, None)
    if returned is not None and time.monotonic() - returned < FRESH_SECONDS:
        return
    ConnectionPool.check_connection(connection)


def reset(connection) -> None:
    """Back to the default transaction mode, stamped as just returned.

    The pool calls this with the connection idle; anything raised here makes
    it discard the connection, which is the right outcome for one that cannot
    even change modes.
    """
    if connection.autocommit:
        connection.autocommit = False
    setattr(connection, _RETURNED_AT, time.monotonic())
