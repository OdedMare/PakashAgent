"""Which key signs session cookies, and the guard when none can be shared.

`main.py` is a composition root that runs at import, so this drives the
decision function rather than importing the module under each environment.
"""

import subprocess
import sys

import pytest


def _boot(env_extra):
    """Import `app.main` in a fresh interpreter under the given environment."""
    import os

    env = dict(os.environ)
    env.pop("PAKASH_SESSION_SECRET", None)
    # The child interpreter does not inherit pytest's import path.
    backend = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [backend, env.get("PYTHONPATH")]))
    env.update(env_extra)
    return subprocess.run(
        [sys.executable, "-c", "import app.main"],
        capture_output=True, text=True, env=env,
    )


# No database: the one case left where the key is generated per process.
_NO_DATABASE = {"PAKASH_DATABASE_URL": ""}


def test_a_single_worker_starts_without_a_secret():
    """Generating one per process is fine when there is only one process --
    sessions die on restart, which is acceptable for a dev run."""
    result = _boot({"WEB_CONCURRENCY": "1", **_NO_DATABASE})
    assert result.returncode == 0
    assert "PAKASH_SESSION_SECRET is not set" in result.stderr + result.stdout


def test_multiple_workers_without_a_secret_refuse_to_start():
    """Each worker would sign with its own key and reject the others'
    cookies. The symptom is bosses logged out at random, which reads as a
    session bug rather than a missing environment variable."""
    result = _boot({"WEB_CONCURRENCY": "4", **_NO_DATABASE})
    assert result.returncode != 0
    assert "PAKASH_SESSION_SECRET must be set" in result.stderr


def test_multiple_workers_with_a_secret_start_fine():
    result = _boot({"WEB_CONCURRENCY": "4", "PAKASH_SESSION_SECRET": "s3cret", **_NO_DATABASE})
    assert result.returncode == 0


def test_with_a_database_the_key_is_shared_and_nothing_is_refused():
    """Replicas and workers read one key from the database (D39), so
    several of them need no variable -- and importing touches no database:
    the key is looked up on first use, so a pod may start before it."""
    result = _boot({"WEB_CONCURRENCY": "4",
                    "PAKASH_DATABASE_URL": "postgresql://nobody@127.0.0.1:1/none"})
    assert result.returncode == 0
    assert "PAKASH_SESSION_SECRET" not in result.stderr + result.stdout
    assert "Connection refused" not in result.stderr + result.stdout


@pytest.mark.parametrize(
    "name", ["WEB_CONCURRENCY", "UVICORN_WORKERS", "GUNICORN_WORKERS"]
)
def test_every_spelling_of_the_worker_count_is_honoured(name):
    """`WEB_CONCURRENCY` is what uvicorn and gunicorn read; the others are
    what a compose file is likely to say."""
    result = _boot({name: "3", **_NO_DATABASE})
    assert result.returncode != 0
