"""Application console logging.

Uvicorn configures only its own loggers, so without this every ``logger.info``
in the codebase writes to a handler that does not exist and is silently
dropped.

Verbosity is driven by ``PAKASH_LOG_LEVEL`` (default ``INFO``).

Nothing here may log an API key or a prompt carrying employee personal
details — see backend/CLAUDE.md.
"""

import logging
import os
import sys
import threading

_CONFIGURED = False
_LOCK = threading.Lock()

# A 401 answered to one of these is a visitor without a session reading
# anyway, not an event: see `_Quiet401`.
QUIET_401_METHODS = frozenset({"GET", "HEAD"})

_FORMAT = "%(asctime)s %(levelname)-5s [%(threadName)s] %(name)s | %(message)s"
_DATEFMT = "%H:%M:%S"


def configure_logging() -> None:
    """Attach one stdout handler to the root logger, exactly once."""
    global _CONFIGURED
    with _LOCK:
        if _CONFIGURED:
            return
        _CONFIGURED = True

    level = os.getenv("PAKASH_LOG_LEVEL", "INFO").upper()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_FORMAT, datefmt=_DATEFMT))

    root = logging.getLogger()
    root.setLevel(getattr(logging, level, logging.INFO))
    root.addHandler(handler)

    # These two are noisy at DEBUG and say nothing about our own behavior.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    # Uvicorn writes one access line per request. The 401s among them are
    # browsers without a session — every visit probes `/me` first, and an
    # open screen whose cookie died keeps polling — and they drowned out
    # everything else. At DEBUG they are kept, for whoever is tracing one.
    if root.level > logging.DEBUG:
        logging.getLogger("uvicorn.access").addFilter(_Quiet401())

    logging.getLogger("pakash.boot").info(
        "logging configured level=%s (set PAKASH_LOG_LEVEL=DEBUG for more)",
        level,
    )


class _Quiet401(logging.Filter):
    """Drop uvicorn's access line for a 401 on a read.

    A refused POST stays: that is a wrong password or passcode, and a run of
    them is worth seeing even though the throttle already stops it.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        # Uvicorn's access record: (client, method, path, http_version, status).
        args = record.args
        if isinstance(args, tuple) and len(args) == 5:
            method, status = args[1], args[4]
            if status == 401 and method in QUIET_401_METHODS:
                return False
        return True


def trace(name: str) -> logging.Logger:
    """A logger under the shared ``pakash`` prefix."""
    return logging.getLogger("pakash." + name)
