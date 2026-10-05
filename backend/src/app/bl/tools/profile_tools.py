"""What the interview never taught, and what each gap costs."""

from typing import List

from app.bl.tools.period_tools import Tool
from app.bl.tools.values import employees, shifts, text


class ProfileGaps(Tool):
    """The answer to *"מה אתה עוד לא יודע"*.

    The profile carries its own `completeness` record (written by
    `interview_service.end`), so this reports what was already decided rather
    than re-deriving it. **Read-only**: naming a gap does not fill it, and an
    agent that could record the answer would be conducting the interview from
    the control room (D19). `blocks` says which gaps stop a grid outright.
    """

    def __call__(self, team_id: str) -> dict:
        profile = self._reads.profile(team_id)
        if not profile:
            return {
                "found": False, "complete": False,
                "reason": "לא נערך ראיון היכרות עדיין",
            }
        completeness = profile.get("completeness")
        if not isinstance(completeness, dict):
            # No record means the interview was confirmed the ordinary way,
            # through a gate that refuses to finish owing a required field.
            return {"found": True, "complete": True, "gaps": [], "blocks": []}
        missing = _lines(completeness.get("missing_topics"))
        return {
            "found": True,
            "complete": bool(completeness.get("complete")),
            # What the scheduler cannot run without.
            "gaps": missing,
            # What the agent itself flagged as unsettled.
            "open_points": [
                line for line in _lines(completeness.get("open_points"))
                if line not in missing
            ],
            "blocks": blocked_by(profile),
            "has_shifts": bool(shifts(profile)),
            "has_employees": bool(employees(profile)),
        }


def _lines(value) -> List[str]:
    return [line for line in (text(item) for item in value or []) if line]


def blocked_by(profile: dict) -> List[str]:
    """What a partial profile actually prevents, in the manager's terms.

    No shift vocabulary is the only true stop: D9 forbids inventing shifts, so
    neither the agent nor the manager can build a week. Everything else
    degrades rather than blocks.
    """
    blocks = []
    if not shifts(profile):
        blocks.append("בלי סוגי משמרות אין לוח לבנות — לא לסוכן ולא ידנית.")
    if not employees(profile):
        blocks.append("בלי עובדים אין את מי לשבץ.")
    if not profile.get("rules"):
        blocks.append("בלי כללים הסוכן ישבץ בלי להכיר את המגבלות שלכם.")
    return blocks
