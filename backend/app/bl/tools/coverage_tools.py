"""What is missing: short slots, and what stands before publishing."""

from typing import Dict, List

from app.bl.audit import counts_toward_staffing
from app.bl.tools.period_tools import Tool
from app.bl.tools.values import employees, iso, number, period_view, shifts, text

# How many gaps are worth naming in one answer. A period missing thirty
# people is missing a schedule, not a shift, and listing all thirty buries
# the one the manager asked about.
_MAX_GAPS = 12


class CoverageGaps(Tool):
    """Slots carrying fewer people than they ask for, worst first.

    Derived from the stored grid rather than the assignments: a slot with
    nobody on it leaves no assignment row. Counted in seats, not bodies --
    somebody shadowing the shift is not one of the people it asked for
    (`audit.counts_toward_staffing` is the one rule both read).
    """

    def __call__(
        self, team_id: str, day: str = "", schedule_id: str = "",
        starts_on: str = "", ends_on: str = "",
    ) -> dict:
        schedule = self._reads.schedule(team_id, day=day, schedule_id=schedule_id)
        if schedule is None:
            return {"found": False, "gaps": [], "reason": "אין סידור מאוחסן"}
        profile = self._reads.profile(team_id)
        counts = _seat_counts(schedule, profile)
        first, last = iso(starts_on), iso(ends_on)
        gaps = [
            gap for gap in (
                _gap(slot, counts) for slot in schedule.get("slots") or []
                if (not first or iso(slot.get("slot_date")) >= first)
                and (not last or iso(slot.get("slot_date")) <= last)
            )
            if gap is not None
        ]
        # Worst first, then chronological: the emptiest slot is the one that
        # leaves nobody on the floor.
        gaps.sort(key=lambda row: (-row["missing"], row["date"], row["shift"]))
        return {
            "found": True,
            "schedule": period_view(schedule),
            "gaps": gaps[:_MAX_GAPS],
            "total_gaps": len(gaps),
            "people_short": sum(row["missing"] for row in gaps),
            "shift_names": [text(row.get("name")) for row in shifts(profile)],
        }


def _seat_counts(schedule: dict, profile: dict) -> Dict[tuple, int]:
    roster = {
        text(person.get("name")): person
        for person in employees(profile) if text(person.get("name"))
    }
    counts: Dict[tuple, int] = {}
    for row in schedule.get("assignments") or []:
        if counts_toward_staffing(roster.get(text(row.get("employee"))), profile):
            key = (text(row.get("shift")), iso(row.get("date")))
            counts[key] = counts.get(key, 0) + 1
    return counts


def _gap(slot: dict, counts: Dict[tuple, int]):
    shift_name, date = text(slot.get("shift_name")), iso(slot.get("slot_date"))
    headcount = int(number(slot.get("headcount"), 1))
    assigned = counts.get((shift_name, date), 0)
    if assigned >= number(slot.get("headcount"), 1):
        return None
    return {
        "shift": shift_name,
        "date": date,
        "headcount": headcount,
        "assigned": assigned,
        "missing": headcount - assigned,
        "why": "חסרים %d ב%s בתאריך %s." % (headcount - assigned, shift_name, date),
    }


class PublishReadiness(Tool):
    """What stands between this period and the team seeing it.

    Gathers the gaps, the warnings and the pending employee requests -- the
    three things a manager checks by hand before pressing publish.
    **`ready` is a description, not a gate** (D3): nothing branches on it.
    """

    def __init__(self, reads, coverage_gaps: CoverageGaps):
        super().__init__(reads)
        self._coverage_gaps = coverage_gaps

    def __call__(self, team_id: str, day: str = "", schedule_id: str = "") -> dict:
        schedule = self._reads.schedule(team_id, day=day, schedule_id=schedule_id)
        if schedule is None:
            return {
                "found": False, "ready": False,
                "reason": "אין סידור מאוחסן לתאריך הזה",
            }
        profile = self._reads.profile(team_id)
        warnings = self._reads.warnings(team_id, schedule, profile)
        gaps = self._coverage_gaps(team_id, schedule_id=text(schedule.get("id")))
        pending = self._reads.pending_requests(team_id)
        blockers = _blockers(gaps, warnings, pending)
        return {
            "found": True,
            "schedule": period_view(schedule),
            "status": text(schedule.get("status")),
            "published": text(schedule.get("status")) == "published",
            # Descriptive only. Nothing branches on this before a publish.
            "ready": not blockers,
            "blockers": blockers,
            "gaps": gaps.get("gaps") or [],
            "warnings": warnings,
            "pending_requests": pending,
        }


def _blockers(gaps: dict, warnings: List[dict], pending: List[dict]) -> List[str]:
    blockers = []
    if gaps.get("people_short"):
        blockers.append(
            "חסרים %d שיבוצים ב-%d משמרות."
            % (gaps["people_short"], gaps.get("total_gaps", 0))
        )
    serious = [row for row in warnings if text(row.get("severity")) == "warning"]
    if serious:
        blockers.append("יש %d אזהרות פתוחות בסידור." % len(serious))
    if pending:
        blockers.append("יש %d בקשות אילוץ שממתינות להחלטה." % len(pending))
    return blockers
