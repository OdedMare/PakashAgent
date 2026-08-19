"""The multi-worker session-secret guard.

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
    env.update(env_extra)
    return subprocess.run(
        [sys.executable, "-c", "import app.main"],
        capture_output=True, text=True, env=env,
    )


def test_a_single_worker_starts_without_a_secret():
    """Generating one per process is fine when there is only one process --
    sessions die on restart, which is acceptable for a dev run."""
    result = _boot({"WEB_CONCURRENCY": "1"})
    assert result.returncode == 0
    assert "PAKASH_SESSION_SECRET is not set" in result.stderr + result.stdout


def test_multiple_workers_without_a_secret_refuse_to_start():
    """Each worker would sign with its own key and reject the others'
    cookies. The symptom is bosses logged out at random, which reads as a
    session bug rather than a missing environment variable."""
    result = _boot({"WEB_CONCURRENCY": "4"})
    assert result.returncode != 0
    assert "PAKASH_SESSION_SECRET must be set" in result.stderr


def test_multiple_workers_with_a_secret_start_fine():
    result = _boot({"WEB_CONCURRENCY": "4", "PAKASH_SESSION_SECRET": "s3cret"})
    assert result.returncode == 0


@pytest.mark.parametrize(
    "name", ["WEB_CONCURRENCY", "UVICORN_WORKERS", "GUNICORN_WORKERS"]
)
def test_every_spelling_of_the_worker_count_is_honoured(name):
    """`WEB_CONCURRENCY` is what uvicorn and gunicorn read; the others are
    what a compose file is likely to say."""
    result = _boot({name: "3"})
    assert result.returncode != 0
