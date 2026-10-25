"""Worker lanes and generation jobs stay small enough for chat to pass."""

from contextlib import contextmanager

from app.worker import JobWorker


class _Repository:
    def __init__(self, jobs=()):
        self.jobs = list(jobs)
        self.lanes = []
        self.finished = []
        self.reconciled = []

    def list_teams(self):
        return []

    @contextmanager
    def claim_copilot_job(self, lane="any"):
        self.lanes.append(lane)
        yield self.jobs.pop(0) if self.jobs else None

    def finish_copilot_job(self, job_id, error="", retry=False):
        self.finished.append((job_id, error, retry))

    def generation_activity(self, *_args):
        pass

    def queue_generation_job(self, team_id, schedule_id):
        self.reconciled.append((team_id, schedule_id))


class _Schedules:
    def __init__(self):
        self.calls = []

    def run_generation(self, *args):
        self.calls.append(args)


def test_worker_claims_only_its_lane():
    repository = _Repository()
    worker = JobWorker(repository)

    assert worker.run_once("interactive") == 0
    assert repository.lanes == ["interactive"]


def test_generation_job_runs_one_named_span_then_reconciles_queue():
    job = {
        "id": "job-1", "team_id": "team-a", "kind": "generation",
        "attempts": 1,
        "payload": {
            "schedule_id": "schedule-1", "date": "2026-10-20",
            "through": "2026-10-20",
        },
    }
    repository = _Repository([job])
    schedules = _Schedules()
    worker = JobWorker(repository, schedules=schedules)

    assert worker.run_once("background") == 1
    assert schedules.calls == [
        ("team-a", "schedule-1", "2026-10-20", "2026-10-20")
    ]
    assert repository.reconciled == [("team-a", "schedule-1")]
    assert repository.finished == [("job-1", "", False)]


def test_a_leftover_copilot_scan_is_finished_without_running_anything():
    """The copilot is gone, but an existing database may still hold scans."""
    job = {"id": "job-2", "team_id": "team-a", "kind": "scan",
           "attempts": 1, "payload": {}}
    repository = _Repository([job])

    assert JobWorker(repository).run_once("background") == 1
    assert repository.finished == [("job-2", "", False)]
