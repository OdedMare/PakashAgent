"""`TranslationTools`: what the translating agent may ask while it works.

Pure Python over the profile, the period and the constraints it was handed.
No model call, no repository, no write: `dry_run` schedules in memory and
returns findings, never rows to store. Every result is a plain dict the
loop hands back to the model verbatim, and an error is a result too
(`ok: false`), never an exception, so one bad call cannot end the loop.
"""

from typing import Any, Dict, List

from app.bl.schedule_requests import covers, read_requests
from app.bl.scheduler.availability import effective_availability
from app.bl.scheduler.directives import translated_row
from app.bl.scheduler.slots import build_slots
from app.bl.shared import text, weekday_key
from app.common.errors import AgentError

_MAX_SLOTS = 120
_MAX_FINDINGS = 15


class TranslationTools:
    def __init__(self, profile: dict, starts_on: str, ends_on: str, sources: List[dict],
                 availability=None, history=None, required_assignments=None,
                 already_scheduled=None):
        self.profile, self.starts_on, self.ends_on = profile, starts_on, ends_on
        self.sources = sources
        self.availability = list(availability or [])
        self.history = history
        self.required_assignments = list(required_assignments or [])
        self.already_scheduled = already_scheduled
        self.slots = build_slots(profile, starts_on, ends_on)
        self.people = {
            text(row.get("name")): row for row in (profile or {}).get("employees") or []
            if isinstance(row, dict) and text(row.get("name"))
        }
        self.standing = {row["id"] for row in sources if row.get("persistent")}
        self.shifts = {text(row.get("name")) for row in (profile or {}).get("shifts") or []
                       if isinstance(row, dict)}

    def run(self, tool: str, arguments: Dict[str, Any]) -> dict:
        handler = getattr(self, "_" + tool, None) if tool in _TOOLS else None
        if handler is None:
            return {"tool": tool, "ok": False, "error": "unknown tool"}
        try:
            return dict(handler(arguments or {}), tool=tool)
        except AgentError as exc:
            return {"tool": tool, "ok": False, "error": str(exc)}

    def _resolve_employee(self, arguments: dict) -> dict:
        from app.bl.tools import resolve_employee

        found = resolve_employee(self.profile, text(arguments.get("name")))
        return {"ok": True, "name": text(arguments.get("name")), "found": found["found"],
                "ambiguous": found["ambiguous"], "matches": found["matches"]}

    def _list_slots(self, arguments: dict) -> dict:
        narrowing = {
            "shifts": _texts(arguments.get("shifts")),
            "dates": _texts(arguments.get("dates")),
            "weekdays": [weekday_key(day) for day in _texts(arguments.get("weekdays"))],
        }
        matched = [
            {"date": slot["slot_date"], "weekday": slot["weekday"], "shift": slot["shift_name"]}
            for slot in self.slots
            if covers(narrowing, slot["shift_name"], slot["slot_date"])
        ]
        return {"ok": True, "count": len(matched), "slots": matched[:_MAX_SLOTS],
                "truncated": len(matched) > _MAX_SLOTS}

    def _employee_state(self, arguments: dict) -> dict:
        name = text(arguments.get("name"))
        person = self.people.get(name)
        if person is None:
            return {"ok": False, "error": "not on the roster; call resolve_employee first"}
        blocked = [
            {"date": row["date"], "shift": row.get("shift") or "", "reason": row.get("reason") or ""}
            for row in effective_availability(self.profile, self.availability,
                                              self.starts_on, self.ends_on)
            if text(row.get("employee")) == name and row.get("is_hard", True) is not False
            and not row.get("available")
        ]
        return {
            "ok": True, "name": name,
            "eligible_shifts": person.get("eligible_shifts") or [],
            "roles": sorted({text(role) for role in person.get("roles") or [] if text(role)}
                            | ({text(person.get("role"))} if text(person.get("role")) else set())),
            "is_shift_manager": bool(person.get("is_shift_manager")),
            "rotation_group": text(person.get("rotation_group")),
            "hard_unavailable": blocked[:_MAX_FINDINGS],
        }

    def _check(self, arguments: dict) -> dict:
        directives, requests, problems = self._read_drafts(arguments)
        covered = {row["source_id"] for _, row in directives}
        covered.update(row["source_id"] for row in requests)
        missing = [row["id"] for row in self.sources if row["id"] not in covered]
        return {"ok": not problems, "problems": problems,
                "accepted_directives": len(directives), "accepted_requests": len(requests),
                "sources_not_covered": missing}

    def _dry_run(self, arguments: dict) -> dict:
        from app.bl.deterministic_scheduler import generate_span

        directives, requests, problems = self._read_drafts(arguments)
        absent = [row for kind, row in directives if kind == "unavailable"]
        pins = [row for kind, row in directives if kind == "required_assignment"]
        result = generate_span(
            self.profile, self.starts_on, self.ends_on,
            availability=self.availability + absent, history=self.history,
            required_assignments=self.required_assignments + pins,
            already_scheduled=self.already_scheduled, requests=requests,
        )
        warnings = [row.get("message") for row in result["warnings"]
                    if row.get("severity") == "warning"]
        return {
            "ok": not warnings and not problems,
            "skipped_as_invalid": problems,
            "assignments": len(result["assignments"]),
            "warnings": warnings[:_MAX_FINDINGS],
            "broken_soft_requests": result["notes"][:_MAX_FINDINGS],
        }

    def _read_drafts(self, arguments: dict):
        """Valid directives as (action, row) pairs, valid requests, and a
        line per refused item saying why."""
        problems, directives = [], []
        source_ids = {row["id"] for row in self.sources}
        slots = {(slot["shift_name"], slot["slot_date"]) for slot in self.slots}
        for index, row in enumerate(_rows(arguments.get("directives")), start=1):
            read = translated_row(row, source_ids, self.people, slots, self.standing, self.shifts)
            if read is None:
                problems.append("directive %d: %s" % (index, _directive_problem(
                    row, source_ids, self.people, slots, self.standing)))
            else:
                directives.append((read[1], dict(read[2], source_id=read[0])))
        requests, errors = read_requests(_rows(arguments.get("requests")), self.profile)
        problems.extend("request: %s" % error for error in errors)
        for row in requests:
            if row["source_id"] not in source_ids:
                problems.append("request: unknown source_id %s" % (row["source_id"] or "(empty)"))
        requests = [row for row in requests if row["source_id"] in source_ids]
        return directives, requests, problems


def _directive_problem(row: Any, source_ids: set, people: dict, slots: set,
                       standing: set = frozenset()) -> str:
    if not isinstance(row, dict):
        return "not an object"
    employee, shift, date = text(row.get("employee")), text(row.get("shift")), text(row.get("date"))
    if row.get("source_id") not in source_ids:
        return "unknown source_id"
    if row.get("action") not in ("unavailable", "required_assignment"):
        return "unknown action"
    if employee not in people:
        return "%s is not on the roster" % (employee or "(empty)")
    if row.get("source_id") in standing and (shift, date) not in slots:
        return "no shift %s, or %s is not an ISO date" % (shift or "(empty)", date or "(empty)")
    if (shift, date) not in slots:
        return "no slot %s on %s in this period" % (shift or "(empty)", date or "(empty)")
    if not text(row.get("reason")):
        return "missing reason"
    return "%s is not eligible for %s" % (employee, shift)


def _rows(value: Any) -> List[dict]:
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _texts(value: Any) -> List[str]:
    return [text(item) for item in value if text(item)] if isinstance(value, list) else []


_TOOLS = ("resolve_employee", "list_slots", "employee_state", "check", "dry_run")

__all__ = ["TranslationTools"]
