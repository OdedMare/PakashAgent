"""Progress for the current job, without coupling model code to storage."""

from contextlib import contextmanager
from contextvars import ContextVar

_reporter = ContextVar("job_activity", default=None)


@contextmanager
def track_activity(reporter):
    token = _reporter.set(reporter)
    try:
        yield
    finally:
        _reporter.reset(token)


def report_activity(activity):
    reporter = _reporter.get()
    if reporter is not None:
        reporter(activity)
