"""Which key signs session cookies, decided once at start-up (D39).

Every process of a deployment must sign with the same key, or a cookie
issued by one is refused by the next and bosses are logged out at random.
In order of preference:

1. `PAKASH_SESSION_SECRET`, when set -- the operator chose it.
2. One generated key kept in PostgreSQL (`deployment_state`), claimed by
   whichever process asks first and read back by every other. Replicas,
   the worker and restarts all agree without anyone setting a variable.
3. With no database at all, a key for this process alone -- fine for one
   dev worker, refused when the server says it runs several.
"""

import logging
import os

from app.common.sessions import SharedSecret, generate_secret

_log = logging.getLogger("pakash.api")

_KEY = "session_secret"


def worker_count() -> int:
    """How many workers this process is one of, as the server was told.

    Read from the environment rather than from uvicorn: by the time this
    module is imported the worker is already forked and has no handle on the
    parent's arguments. Both spellings are checked because `WEB_CONCURRENCY`
    is what uvicorn and gunicorn both honour, while `UVICORN_WORKERS` is what
    a compose file is likely to say.
    """
    for name in ("WEB_CONCURRENCY", "UVICORN_WORKERS", "GUNICORN_WORKERS"):
        try:
            count = int(os.getenv(name, ""))
        except ValueError:
            continue
        if count > 0:
            return count
    return 1


def session_key(env, store, repository):
    """The secret to hand every router: a string, or a `SharedSecret`."""
    if env.session_secret:
        return env.session_secret
    if getattr(store.get(), "database_url", ""):
        # Looked up on first use: the database may still be starting.
        return SharedSecret(
            lambda: repository.claim_deployment_value(_KEY, generate_secret())
        )
    # Refused rather than warned about when there is more than one worker.
    # The symptom is bosses being logged out at random with every request
    # that happens to land on a different worker — which reads as a session
    # bug, not as a missing environment variable, and costs hours to trace
    # back to here. A start-up that fails with the variable's name in the
    # message costs seconds.
    if worker_count() > 1:
        raise RuntimeError(
            "PAKASH_SESSION_SECRET must be set when running more than one "
            "worker without a database: each worker would sign session "
            "cookies with its own generated key and reject every cookie "
            "signed by the others. Generate one with: "
            "python -c \"import secrets; print(secrets.token_urlsafe(32))\""
        )
    _log.warning(
        "PAKASH_SESSION_SECRET is not set and there is no database; generated "
        "one for this process. Sessions will not survive a restart."
    )
    return generate_secret()
