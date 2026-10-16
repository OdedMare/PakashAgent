"""The copilot observes durably and keeps every write behind a boundary."""

import datetime

from app.bl.copilot import CopilotService


class _Repo:
    def __init__(self, mode="suggest"):
        self.mode = mode
        self.created = []
        self.transitions = []
        self.items = {}

    def team_profile(self, _team):
        return {"completeness": {
            "complete": False,
            "missing_topics": ["מי מוסמך למשמרת הלילה?"],
            "open_points": [],
        }}

    def latest_profile_updated_at(self, _team):
        return datetime.datetime.now(datetime.timezone.utc)

    def copilot_permission(self, _team, _action):
        return self.mode

    def create_copilot_item(
        self, team, fingerprint, kind, action, title, detail, payload, job
    ):
        item = {
            "id": "item-%s" % (len(self.created) + 1),
            "team_id": team, "fingerprint": fingerprint, "kind": kind,
            "action_type": action, "title": title, "detail": detail,
            "payload": payload, "status": "pending", "source_job_id": job,
        }
        self.created.append(item)
        self.items[item["id"]] = item
        return item

    def copilot_item(self, item_id, _team):
        return self.items[item_id]

    def transition_copilot_item(
        self, item_id, team, status, before, after, verification, actor="manager"
    ):
        result = dict(self.items[item_id], status=status, after_state=after)
        self.items[item_id] = result
        self.transitions.append((team, status, before, after, verification, actor))
        return result

class _Schedules:
    def current(self, _team):
        return {
            "id": "schedule-1",
            "warnings": [{
                "code": "understaffed", "message": "חסר עובד",
                "employee": "", "date": "2026-08-21", "shift": "לילה",
            }],
        }


def _service(mode="suggest"):
    repo = _Repo(mode)
    return CopilotService(repo, _Schedules()), repo


def test_scan_creates_profile_and_schedule_proposals():
    service, repo = _service()

    created = service.scan("team", "job")

    assert [item["action_type"] for item in created] == [
        "profile_review", "schedule_repair",
    ]
    assert all(item["kind"] == "proposal" for item in created)
    assert created[1]["payload"]["schedule_id"] == "schedule-1"


def test_observe_permission_never_creates_an_actionable_item():
    service, _ = _service("observe")

    assert all(item["kind"] == "observation" for item in service.scan("team"))


def test_approving_profile_review_requests_the_editor():
    service, repo = _service()
    item = service.scan("team")[0]

    approved = service.approve(item["id"], "team")

    assert approved["status"] == "approved"
    assert repo.transitions[-1][4]["check"] == "profile_edit_requested"


def test_rollback_profile_review_keeps_an_audit_state():
    service, repo = _service()
    item = service.scan("team")[0]
    approved = service.approve(item["id"], "team")

    rolled_back = service.rollback(approved["id"], "team")

    assert rolled_back["status"] == "rolled_back"
    assert repo.transitions[-1][4] == {
        "ok": True, "check": "no_side_effect",
    }
