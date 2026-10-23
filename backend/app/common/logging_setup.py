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

    logging.getLogger("pakash.boot").info(
        "logging configured level=%s (set PAKASH_LOG_LEVEL=DEBUG for more)",
        level,
    )


def trace(name: str) -> logging.Logger:
    """A logger under the shared ``pakash`` prefix."""
    return logging.getLogger("pakash." + name)
