"""A מכלול: several workplaces under one commander (D43).

Each workplace stays a team; this owns what is new above them -- the
operator linking teams into a מכלול and setting its commander's password,
the commander signing in and entering a workplace, the combined board, and
the notices that tell a workplace's manager what the commander changed.

Entering a workplace is not a second set of manager routes. The commander
is handed an ordinary boss cookie for that team, marked with the מכלול, so
the board, the chat, statistics and setup all serve them unchanged; the
guards re-check the link on every request (`api/dependencies.py`).
"""

import datetime
import re
from typing import Dict, List, Optional

from app.common.errors import AgentError, NotFoundError

# The combined board reads a month view at most (six weeks): it audits every period of
# every workplace it draws, and a month of six workplaces is a long answer.
_MAX_BOARD_DAYS = 43

# What a commander's write did, in the words the manager reads (D43). The
# first pattern matching `METHOD path` names it; a write matching none is
# still recorded, as a general change. Reads, and writes that only check or
# preview, are left out -- they change nothing the manager needs to hear of.
_QUIET = re.compile(
    r"^POST /api/(schedule/(check|import/preview|departure/preview|propose)"
    r"|profile/rotation-preview|agent/chats(/[^/]+/(stop|messages/[^/]+/dismiss))?$)"
)
_ACTIONS = (
    (r"^POST /api/schedule/(assign|unassign|move|apply)$", "שינה שיבוץ בלוח"),
    (r"^POST /api/schedule/(generate|blank)", "בנה סידור"),
    (r"^POST /api/schedule/[^/]+/publish$", "פרסם סידור"),
    (r"^POST /api/schedule/[^/]+/unpublish$", "החזיר סידור לטיוטה"),
    (r"^(POST /api/schedule/[^/]+/clear|DELETE /api/schedule/[^/]+)$",
     "ניקה או מחק סידור"),
    (r"^POST /api/schedule/departure$", "רשם עזיבה של חייל"),
    (r"^POST /api/schedule/import/confirm$", "ייבא סידור מקובץ"),
    (r"^(POST|DELETE) /api/schedule/constraints", "עדכן אילוצים"),
    (r"^(POST|PATCH|DELETE) /api/schedule/preferences", "עדכן העדפות לסוכן"),
    (r"^POST /api/schedule/(requests|swaps)/", "טיפל בבקשות החיילים"),
    (r"^(PUT|DELETE) /api/profile", "שינה את הגדרות המשמרת"),
    (r"^POST /api/agent/chats/[^/]+/messages/[^/]+/apply$",
     "אישר שינוי מהשיחה עם הסוכן"),
    (r"^POST /api/agent/chats", "שוחח עם הסוכן"),
)
_GENERAL = "ביצע שינוי"


def describe_action(method: str, path: str) -> Optional[str]:
    """The manager-facing words for a commander's request, or None when
    there is nothing to tell (a read, a check, a preview)."""
    method = (method or "").upper()
    if method in ("GET", "HEAD", "OPTIONS"):
        return None
    line = "%s %s" % (method, path.rstrip("/"))
    if _QUIET.match(line):
        return None
    for pattern, words in _ACTIONS:
        if re.match(pattern, line):
            return words
    return _GENERAL


class ComplexService:
    def __init__(self, repository, workspace, schedules=None):
        self._repository = repository
        self._workspace = workspace
        self._schedules = schedules

    # --- the operator --------------------------------------------------------

    def list_for_admin(self) -> List[dict]:
        return self._repository.admin_complexes()

    def create(self, name: str, password: str, team_ids: List[str]) -> dict:
        clean = self._name(name)
        self._workspace.validate_password(password)
        created = self._repository.create_complex(clean, password)
        if team_ids:
            self._repository.set_complex_teams(created["id"], list(team_ids))
        return self._admin_row(created["id"])

    def update(self, complex_id: str, patch: Dict) -> dict:
        fields = {}
        if "name" in patch:
            fields["name"] = self._name(patch["name"])
        if "notes" in patch:
            notes = (patch["notes"] or "").strip()
            if len(notes) > 500:
                raise AgentError("ההערה ארוכה מדי")
            fields["notes"] = notes
        if "active" in patch:
            if not isinstance(patch["active"], bool):
                raise AgentError("מצב המכלול אינו תקין")
            fields["active"] = patch["active"]
        self._repository.update_complex(complex_id, fields)
        if "team_ids" in patch and patch["team_ids"] is not None:
            self._repository.set_complex_teams(complex_id, list(patch["team_ids"]))
        return self._admin_row(complex_id)

    def reset_password(self, complex_id: str, password: str) -> None:
        self._workspace.validate_password(password)
        self._repository.set_complex_password(complex_id, password)

    def delete(self, complex_id: str, confirm_name: str) -> None:
        """Removes the grouping only; every workplace stays as it was."""
        row = self._repository.get_complex(complex_id)
        if (confirm_name or "").strip() != row["name"].strip():
            raise AgentError("כדי למחוק יש להקליד את שם המכלול בדיוק")
        self._repository.delete_complex(complex_id)

    def _admin_row(self, complex_id: str) -> dict:
        for row in self._repository.admin_complexes():
            if row["id"] == complex_id:
                return row
        raise NotFoundError("המכלול לא נמצא")

    @staticmethod
    def _name(name: str) -> str:
        clean = (name or "").strip()
        if not clean:
            raise AgentError("שם המכלול אינו יכול להיות ריק")
        if len(clean) > 80:
            raise AgentError("שם המכלול ארוך מדי")
        return clean

    # --- the commander ---------------------------------------------------------

    def list_public(self) -> List[dict]:
        return [
            {"id": row["id"], "name": row["name"]}
            for row in self._repository.list_complexes()
        ]

    def login(self, complex_id: str, password: str) -> dict:
        row = self._repository.authenticate_commander(complex_id, password)
        if not row.get("active", True):
            raise AgentError("המכלול הושבת על ידי צוות משמרות זהב")
        return {"id": row["id"], "name": row["name"]}

    def describe(self, complex_id: str) -> dict:
        row = self._repository.get_complex(complex_id)
        return {
            "id": row["id"], "name": row["name"],
            "teams": self._repository.complex_teams(complex_id),
        }

    def require_team(self, complex_id: str, team_id: str) -> dict:
        """The team, if it is one of this commander's workplaces and on.
        A team outside the מכלול is a 404, never a distinct refusal."""
        for team in self._repository.complex_teams(complex_id):
            if team["id"] == team_id:
                if not team["active"]:
                    raise AgentError("המשמרת הושבתה על ידי צוות משמרות זהב")
                return team
        raise NotFoundError("המשמרת לא נמצאה")

    def board(self, complex_id: str, start: str, end: str) -> dict:
        """Every workplace's schedule over `start`..`end`, side by side.

        Each workplace is read through the same `periods_between` its own
        board reads, as its boss: drafts included, since the commander holds
        a manager's powers in each."""
        first, last = _date(start), _date(end)
        if first is None or last is None or first > last:
            raise AgentError("טווח התאריכים אינו תקין")
        if (last - first).days >= _MAX_BOARD_DAYS:
            raise AgentError("טווח התאריכים ארוך מדי")
        teams = []
        for team in self._repository.complex_teams(complex_id):
            periods = []
            if team["active"] and self._schedules is not None:
                periods = self._schedules.periods_between(
                    team["id"], start, end, role="boss"
                )
            teams.append(dict(team, periods=[_compact(p) for p in periods]))
        return {"start": start, "end": end, "teams": teams}

    # --- what the manager is told -------------------------------------------------

    def record(self, team_id: str, complex_id: str, action: str) -> None:
        try:
            name = self._repository.get_complex(complex_id)["name"]
        except NotFoundError:
            name = ""
        self._repository.record_commander_notice(team_id, name, action)

    def notices(self, team_id: str) -> dict:
        complex_row = self._repository.team_complex(team_id)
        return {
            "complex": complex_row,
            "notices": self._repository.commander_notices(team_id),
        }

    def mark_seen(self, team_id: str) -> None:
        self._repository.mark_commander_notices_seen(team_id)


def _date(value: str) -> Optional[datetime.date]:
    try:
        return datetime.date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return None


def _compact(period: dict) -> dict:
    """What the combined board draws of a period: its slots and who is on
    them. Not the audit, the notes or the generation state."""
    return {
        "id": period["id"],
        "starts_on": period["starts_on"],
        "ends_on": period["ends_on"],
        "status": period["status"],
        "slots": [
            {
                "shift_name": slot["shift_name"],
                "slot_date": slot["slot_date"],
                "start_time": slot.get("start_time", ""),
                "end_time": slot.get("end_time", ""),
                "headcount": slot.get("headcount", 0),
            }
            for slot in period.get("slots", [])
        ],
        "assignments": [
            {
                "employee": row["employee"],
                "shift": row["shift"],
                "date": row["date"],
            }
            for row in period.get("assignments", [])
        ],
        "warnings": len(period.get("warnings", [])),
    }


__all__ = ["ComplexService", "describe_action"]
