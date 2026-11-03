"""A placement check audits only what the placement can change.

`PlacementContext.verdict` used to audit the whole schedule twice for every
candidate, so the replacement tab on a 70-person roster ran for minutes and
the proxy hung up on it. It now audits the candidate's rows plus the target
slot. These tests hold it to the old answer: every check is about one
person or one slot, so the narrowed audit must attribute exactly the same
warnings to a placement as the whole schedule does.
"""

import copy
import json
import pathlib

from app.bl.audit import audit
from app.bl.placement import values
from app.bl.placement.context import PlacementContext, effective_rows
from app.bl.shared import warning_key
from app.bl.solver import generate_span

SCENARIO = pathlib.Path(__file__).resolve().parents[2] / "devsandbox" / "scenarios" / "unit_619.json"
WEEK = ("2026-11-08", "2026-11-14")


def _profile():
    profile = json.loads(SCENARIO.read_text(encoding="utf-8"))
    profile["rules"] = []
    # Tight limits so placements do trip hours, runs and rest.
    profile["employees"][1]["max_weekly_hours"] = 24
    return profile


def _whole_schedule(context, employee, shift_name, slot_date):
    before = values.rows(context.schedule, drop=context.moving)
    after = before + [{"employee": employee, "shift": shift_name, "date": slot_date}]
    def run(rows):
        return audit(rows, context.shifts, context.employees, context.availability,
                     context.profile, context.slots)
    existing = {warning_key(row) for row in run(before)}
    return sorted(warning_key(row) for row in run(after) if warning_key(row) not in existing)


def _schedule(profile):
    built = generate_span(profile, *WEEK)
    slots = [dict(slot, slot_date=slot.get("slot_date") or slot.get("date"))
             for slot in built.get("slots") or []]
    rows = [dict(row, id="a%d" % n) for n, row in enumerate(built["assignments"])]
    # A row the board drifted into: overstaffs a slot and breaks a rotation.
    rows.append(dict(rows[0], id="extra", employee=profile["employees"][2]["name"]))
    return {"starts_on": WEEK[0], "ends_on": WEEK[1], "slots": slots, "assignments": rows}


def _availability(profile):
    name = profile["employees"][3]["name"]
    return [{"employee": name, "date": "2026-11-10", "available": False, "is_hard": True,
             "reason": "קורס"}]


def test_the_narrowed_audit_attributes_the_same_warnings_as_the_whole_schedule():
    profile = _profile()
    schedule = _schedule(profile)
    for moving in ("", "a3"):
        context = PlacementContext(
            schedule, profile,
            effective_rows(schedule, profile, _availability(profile), WEEK[0]), moving)
        pairs = sorted({(slot["shift_name"], slot["slot_date"]) for slot in context.slots})
        checked = 0
        for person in profile["employees"][::3]:
            for shift_name, slot_date in pairs[::2]:
                narrow = sorted(warning_key(row) for row in
                                context.verdict(person["name"], shift_name, slot_date)["warnings"])
                assert narrow == _whole_schedule(context, person["name"], shift_name, slot_date)
                checked += 1
        assert checked > 50


def test_a_schedule_without_a_grid_is_checked_the_same_way():
    profile = _profile()
    schedule = dict(_schedule(profile), slots=[])
    context = PlacementContext(schedule, profile, [])
    for person in profile["employees"][:6]:
        for shift in profile["shifts"]:
            narrow = sorted(warning_key(row) for row in
                            context.verdict(person["name"], shift["name"], "2026-11-11")["warnings"])
            assert narrow == _whole_schedule(context, person["name"], shift["name"], "2026-11-11")
