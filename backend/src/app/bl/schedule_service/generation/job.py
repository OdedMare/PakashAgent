"""The checkpoint document of one range build, and its state transitions.

Stored on the schedule as `generation` and read back by the browser's poll.
Every transition the worker makes -- start a span, finish it, fail it, stop,
requeue -- is a method here, so the counters (`completed_days`,
`failed_days`) are recomputed in one place instead of at every call site.
"""

import datetime
from typing import List, Optional

from app.bl.scheduler.planning import split_dates
from app.bl.scheduler.quality import combine_metrics

from app.bl.schedule_service.constants import (
    ERROR_LIMIT,
    GENERATION_CANCELLED,
    GENERATION_COMPLETE,
    GENERATION_FAILED,
    GENERATION_PENDING,
    GENERATION_RUNNING,
    INSTRUCTIONS_LIMIT,
    SUMMARY_LIMIT,
)
from app.bl.schedule_service.rows import iso, now_stamp, text

# A span the worker may still take: never started, interrupted, or failed.
_TAKEABLE = (GENERATION_FAILED, GENERATION_RUNNING, GENERATION_PENDING)


def span_dates(entry: dict) -> List[str]:
    """The dates one checkpoint entry covers.

    Derived from `date`/`through` when `dates` is absent, so a job opened
    before spans existed — one already checkpointed and half finished when
    the code was deployed — resumes as the run of single days it is, rather
    than failing on a field its stored state never had.
    """
    stored = entry.get("dates")
    if isinstance(stored, list) and stored:
        return [iso(item) for item in stored if iso(item)]
    first = iso(entry.get("date"))
    last = iso(entry.get("through")) or first
    try:
        start = datetime.date.fromisoformat(first)
        end = datetime.date.fromisoformat(last)
    except (TypeError, ValueError):
        return [first] if first else []
    dates = []
    while start <= end:
        dates.append(start.isoformat())
        start += datetime.timedelta(days=1)
    return dates


def span_entry(first: str, through: str, dates: List[str]) -> dict:
    return {
        "date": first,
        "through": through,
        "dates": dates,
        "status": GENERATION_PENDING,
        "attempts": 0,
        "error": "",
        "metrics": {},
    }


class GenerationJob:
    def __init__(self, document: Optional[dict]):
        self._document = dict(document or {})
        self.days = [dict(item) for item in self._document.get("days") or []]

    @classmethod
    def of(cls, schedule: dict) -> "GenerationJob":
        return cls(schedule.get("generation"))

    @classmethod
    def open(
        cls,
        spans: List[dict],
        total_days: int,
        mode: str,
        instructions: str,
        required: List[dict],
    ) -> "GenerationJob":
        """A fresh job, running, with every span pending.

        Progress is counted in dates, never in spans: the bar means "days of
        the period", and a week-wide job whose counter moved by seven at a
        time would read as a bar that jumps rather than fills. The heartbeat
        is stamped now so the browser has something to compare against
        before the first worker beat lands.
        """
        return cls({
            "status": GENERATION_RUNNING,
            "current_date": spans[0]["date"] if spans else "",
            "total_days": total_days,
            "completed_days": 0,
            "failed_days": 0,
            "mode": mode,
            "instructions": text(instructions)[:INSTRUCTIONS_LIMIT],
            "required_assignments": required or [],
            "notes": [],
            "summaries": [],
            "heartbeat": now_stamp(),
            "cancel_requested": False,
            "days": [
                span_entry(span["date"], span["through"], span["dates"])
                for span in spans
            ],
        })

    # -- reading -------------------------------------------------------------

    def get(self, key: str, default=None):
        return self._document.get(key, default)

    @property
    def status(self) -> str:
        return self._document.get("status") or ""

    @property
    def is_complete(self) -> bool:
        return self.status == GENERATION_COMPLETE

    @property
    def cancel_requested(self) -> bool:
        return bool(self._document.get("cancel_requested"))

    def next_target(self) -> Optional[dict]:
        return next(
            (day for day in self.days if day.get("status") in _TAKEABLE), None
        )

    def first_failed(self) -> Optional[dict]:
        return next(
            (day for day in self.days
             if day.get("status") == GENERATION_FAILED),
            None,
        )

    def first_unfinished(self) -> Optional[dict]:
        return next(
            (day for day in self.days
             if day.get("status") != GENERATION_COMPLETE),
            None,
        )

    def summary(self) -> str:
        return text(" ".join(self._document.get("summaries") or []))[
            :SUMMARY_LIMIT
        ]

    def notes(self) -> List[str]:
        return self._document.get("notes") or []

    def to_dict(self) -> dict:
        document = dict(self._document)
        document["days"] = self.days
        return document

    # -- transitions ---------------------------------------------------------

    def resume(self) -> None:
        """Back to running, with the stop flag cleared."""
        self._document.update({
            "status": GENERATION_RUNNING,
            "cancel_requested": False,
            "dismissed": False,
            "heartbeat": now_stamp(),
        })

    def start_span(self, target: dict) -> None:
        target.update({
            "status": GENERATION_RUNNING,
            "attempts": int(target.get("attempts") or 0) + 1,
            "error": "",
        })
        self._document.update({
            "status": GENERATION_RUNNING,
            "current_date": iso(target.get("date")),
            "heartbeat": now_stamp(),
        })

    def complete_span(self, target: dict, result: dict) -> None:
        target.update({
            "status": GENERATION_COMPLETE,
            "error": "",
            "metrics": combine_metrics(target.get("metrics") or {}, result.get("metrics") or {}),
        })
        self._document.setdefault("notes", []).extend(result.get("notes") or [])
        summary = text(result.get("summary"))
        if summary:
            self._document.setdefault("summaries", []).append(summary)
        self.recount()

    def fail_span(self, target: dict, error: Exception) -> None:
        target.update({
            "status": GENERATION_FAILED, "error": str(error)[:ERROR_LIMIT],
            "metrics": combine_metrics(target.get("metrics") or {},
                                       getattr(error, "generation_metrics", {})),
        })
        self._document.update({
            "status": GENERATION_FAILED,
            "current_date": iso(target.get("date")),
        })
        self.recount()

    def split(self, target: dict) -> bool:
        """Checkpoint smaller pending requests; never re-ask completed neighbours."""
        halves = split_dates(span_dates(target))
        if self.cancel_requested or not halves:
            return False
        children = [span_entry(dates[0], dates[-1], dates) for dates in halves]
        # Keep the failed parent call's cost exactly once, on its first child.
        children[0]["metrics"] = combine_metrics(target.get("metrics") or {}, {"split_count": 1})
        index = self.days.index(target)
        self.days[index:index + 1] = children
        self._document["status"] = GENERATION_RUNNING
        self._document["current_date"] = children[0]["date"]
        self.recount()
        return True

    def advance(self) -> bool:
        """Point at the next unfinished span. True once nothing is left."""
        remaining = self.first_unfinished()
        if remaining is None:
            self._document.update({
                "status": GENERATION_COMPLETE, "current_date": "",
            })
            return True
        self._document.update({
            "status": GENERATION_RUNNING,
            "current_date": iso(remaining.get("date")),
        })
        return False

    def mark_complete(self) -> None:
        self._document["status"] = GENERATION_COMPLETE

    def stop(self) -> None:
        """Park the job the manager stopped, keeping every finished day."""
        self._release_running()
        self._document.update({
            "status": GENERATION_CANCELLED,
            "cancel_requested": True,
        })
        self.recount()

    def dismiss(self) -> None:
        """Hide the banner of a job that ended short, without touching it.

        The days it built stay and resuming still works; only the board stops
        announcing it. A later resume clears the flag again."""
        self._document["dismissed"] = True

    def requeue(self, target: dict) -> None:
        target.update({"status": GENERATION_PENDING})
        self._document["status"] = GENERATION_RUNNING
        self.recount()

    def crash(self, error: Exception) -> bool:
        """Record a worker that died outside a checkpoint.

        Returns False when the job already says why it ended -- a failed
        span or a stop -- so the caller does not overwrite that record.
        """
        if self.status in (GENERATION_FAILED, GENERATION_CANCELLED):
            return False
        self._document.update({
            "status": GENERATION_FAILED,
            "heartbeat": now_stamp(),
            "failed_days": max(1, int(self._document.get("failed_days") or 0)),
        })
        for day in self.days:
            if day.get("status") == GENERATION_RUNNING:
                day.update({
                    "status": GENERATION_FAILED,
                    "error": str(error)[:ERROR_LIMIT],
                })
                break
        return True

    def recount(self) -> None:
        self._document.update({
            "heartbeat": now_stamp(),
            "completed_days": sum(
                len(span_dates(day)) for day in self.days
                if day.get("status") == GENERATION_COMPLETE
            ),
            "failed_days": sum(
                day.get("status") == GENERATION_FAILED for day in self.days
            ),
        })

    def mark_logged(self) -> bool:
        """Flag the change-log entry as written. False if it already was."""
        if self._document.get("logged"):
            return False
        self._document["logged"] = True
        return True

    def _release_running(self) -> None:
        for day in self.days:
            if day.get("status") == GENERATION_RUNNING:
                day["status"] = GENERATION_PENDING
