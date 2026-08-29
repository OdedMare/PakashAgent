"""The facts an agent may ask for while it fills one date, answered in code.

**Pure Python. No LLM call anywhere in this file, and no repository.** A
`DayDraft` is built from the profile, the date's slot grid, the constraints
and what is already scheduled, and it answers four named questions about
that state: which slots are still short, who may legally take one, what a
placement would cost, and how the hours stand. `bl/assignment_agent.py`
runs the loop that asks them; `bl/deterministic_scheduler.py` asks the same
questions in a `for` loop with no model at all.

## Why the two engines share this file

They must agree on one thing above all: **who may legally stand on a slot**.
A candidate list the agent reads and a candidate list the fallback engine
picks from that were computed by two different pieces of code is how a
schedule the manager builds twice comes out legal once — the same failure
`bl/audit.py` names for a coverage bar that disagrees with the warning
below it. So legality, ranking and the hour tally live here, once, and both
engines are callers.

## Blocked is not the same as expensive

Two separate lists come back from `candidates`, and the difference is
[D3](../../../docs/DECISIONS.md#d3--the-agent-decides-code-only-audits-)
drawn exactly where it already runs:

- **`blocked`** — the row is *unusable*: a person or shift nobody declared,
  somebody not qualified for the shift, a hard constraint on the date, a
  closure the rotation gives to another group, a person already standing on
  another shift that day. Code refuses these on the way in, the same class
  of bound `scheduler.py` has always applied to a row naming a person who
  does not exist. Refusing them is not the audit gaining a veto.
- **`costs`** — the row is *legal and expensive*: a sixth consecutive day,
  hours past the person's ceiling, a short rest, a soft availability
  preference the manager wrote down. These stay the agent's to weigh, and
  the agent that takes one is expected to say so — `bl/assignment_agent.py`
  raises an alert for every cost it accepts, which is the loud warning D1
  and D3 promise instead of a gate.

## It answers; it does not persist

A draft holds rows in memory and nothing else. There is no repository here,
so persisting nothing is a property of the wiring rather than a rule
somebody has to remember — the shape `bl/simulate.py` and `bl/changes.py`
already have. `run()`, the dispatch the model reaches, exposes only the four
read-only questions: applying an answer to the draft is `apply()`, which the
loop calls and the model cannot name.
"""

import datetime
from typing import Any, Dict, List, Optional

from app.bl import rotation
from app.bl.audit import (
    CONSECUTIVE,
    CROSS_ROTATION,
    DOUBLE_BOOKED,
    OVER_HOURS,
    SHORT_REST,
    UNAVAILABLE,
    audit,
    constraint_conflicts,
    load_history,
)
from app.common.errors import AgentError

# The named questions. The agent picks from this list and nothing else -- a
# name outside it is a tool that does not exist, and saying so rather than
# improvising is what keeps the model from describing checks it never ran.
TOOL_OPEN_SLOTS = "open_slots"
TOOL_CANDIDATES = "candidates"
TOOL_CHECK_PLACEMENT = "check_placement"
TOOL_WORKLOAD = "workload"

TOOL_NAMES = (
    TOOL_OPEN_SLOTS,
    TOOL_CANDIDATES,
    TOOL_CHECK_PLACEMENT,
    TOOL_WORKLOAD,
)

# What each tool is for, in the manager's language rather than the code's.
# Handed to the model as its menu and rendered in the UI as what the agent
# did, so the two can never describe the tools differently.
TOOL_DESCRIPTIONS = {
    TOOL_OPEN_SLOTS: "אילו משמרות בתאריך עדיין חסרות אנשים, וכמה",
    TOOL_CANDIDATES: "מי יכול/ה לקחת משמרת מסוימת, מי חסום/ה ולמה, ומה המחיר",
    TOOL_CHECK_PLACEMENT: "מה יקרה אם משבצים אדם מסוים למשמרת מסוימת",
    TOOL_WORKLOAD: "כמה שעות צבר כל אחד עד עכשיו, כולל מה שכבר שובץ היום",
}

# Warnings that make a row unusable rather than expensive. A closure
# belonging to another group is the same kind of fact as a shift nobody
# declared, and one person cannot be in two places: a schedule saying
# otherwise is describing a day that cannot happen. A *hard* constraint
# belongs here too and is caught earlier, by `hard_conflict` -- the audit
# raises UNAVAILABLE for a soft preference as well, and only the constraint
# row itself says which of the two it is.
BLOCKING_CODES = frozenset({CROSS_ROTATION, DOUBLE_BOOKED})

# Warnings the agent may accept with its eyes open. Every one of them is a
# real rule and every one of them is sometimes the least bad option at 23:00
# on a Thursday -- which is exactly the judgment D3 keeps with the agent and
# the manager rather than with the code. UNAVAILABLE reaches here only for a
# soft constraint, since a hard one never gets this far.
COST_CODES = frozenset({CONSECUTIVE, OVER_HOURS, SHORT_REST, UNAVAILABLE})


class DayDraft:
    """One date being filled, and the questions that can be asked about it.

    `slots` is the date's grid. `committed` are rows already decided —
    earlier dates of the same build, plus anything standing on this date
    that is not being rebuilt — and they take part in every check without
    ever being returned as this date's answer.
    """

    def __init__(
        self,
        profile: dict,
        day: str,
        slots: List[dict],
        availability: Optional[List[dict]] = None,
        history: Optional[List[dict]] = None,
        committed: Optional[List[dict]] = None,
    ):
        self.profile = profile if isinstance(profile, dict) else {}
        self.day = text(day)
        self.slots = list(slots or [])
        self.availability = [
            row for row in availability or [] if isinstance(row, dict)
        ]
        self.history = [
            row for row in history or [] if isinstance(row, dict)
        ]
        self.shifts = self.profile.get("shifts") or []
        self.employees = employees(self.profile)
        self.people = {text(row.get("name")): row for row in self.employees}
        self.keys = {
            (slot["shift_name"], slot["slot_date"]) for slot in self.slots
        }
        self.rows = unique([
            row for row in [assignment(item) for item in committed or []]
            if row is not None
        ])
        # The audit over the draft as it stands, keyed. Cached because
        # `candidates` asks what *each* person would add and the answer to
        # "what is already wrong" is the same for all of them -- on a real
        # roster that is one audit instead of one per candidate. Dropped
        # whenever the rows move.
        self._standing = None

    # -- the menu ----------------------------------------------------------

    def run(self, name: str, arguments: Optional[dict] = None) -> dict:
        """Dispatch one named tool call. The agent's only entry point.

        Returns `{"tool", "ok", ...}` whatever happens, including for a name
        that does not exist: the caller is a loop that has to be able to feed
        a failure back to the model and carry on, and an exception there ends
        a turn that still had something useful to do.
        """
        arguments = arguments if isinstance(arguments, dict) else {}
        shift = text(arguments.get("shift") or arguments.get("shift_name"))
        if name == TOOL_OPEN_SLOTS:
            return dict(self.open_slots(), tool=name, ok=True)
        if name == TOOL_WORKLOAD:
            return dict(self.workload(), tool=name, ok=True)
        if name == TOOL_CANDIDATES:
            if not shift:
                return {"tool": name, "ok": False,
                        "error": "צריך לציין שם משמרת"}
            return dict(self.candidates(shift), tool=name, ok=True)
        if name == TOOL_CHECK_PLACEMENT:
            employee = text(arguments.get("employee"))
            if not employee or not shift:
                return {"tool": name, "ok": False,
                        "error": "צריך לציין עובד/ת ושם משמרת"}
            return dict(
                self.check_placement(employee, shift), tool=name, ok=True
            )
        return {
            "tool": text(name), "ok": False,
            "error": "אין כלי בשם הזה",
        }

    def open_slots(self) -> dict:
        """Every slot on the date with what it still asks for."""
        return {"date": self.day, "slots": [
            self.slot_state(slot) for slot in self.slots
        ]}

    def slot_state(self, slot: dict) -> dict:
        on = [
            row["employee"] for row in self.rows if same_slot(row, slot)
        ]
        headcount = max(0, int(slot.get("headcount") or 0))
        return {
            "shift": slot["shift_name"],
            "date": slot["slot_date"],
            "start_time": text(slot.get("start_time")),
            "end_time": text(slot.get("end_time")),
            "headcount": headcount,
            "assigned": on,
            # Counted the way `audit.py` counts a seat: somebody shadowing
            # the shift is at work and on the board without filling one.
            "filled": counted_on(self.rows, slot, self.people, self.profile),
            "missing": max(
                0,
                headcount - counted_on(
                    self.rows, slot, self.people, self.profile
                ),
            ),
            "requires_shift_manager": bool(
                slot.get("requires_shift_manager")
            ),
            "has_shift_manager": any(
                person(self.profile, name).get("is_shift_manager")
                for name in on
            ),
            "required_roles": list(slot.get("required_roles") or []),
            "missing_roles": sorted(missing_roles(
                self.rows, slot, self.profile
            )),
        }

    def candidates(self, shift_name: str) -> dict:
        """Who may take this slot, ranked, and who may not, with the reason.

        The ranking is the fallback engine's own order — scarcest capability
        first, then the closing group, then the lightest load — so the list
        the agent reads top-down is the list the code would have picked from.
        It is an ordering, not an instruction: the agent is free to take the
        fourth name and say why, which is the whole point of it deciding.
        """
        slot = self.slot(shift_name)
        if slot is None:
            return {
                "shift": text(shift_name), "date": self.day,
                "found": False,
                "reason": "אין משמרת בשם הזה בתאריך הזה",
                "candidates": [], "blocked": [],
            }

        loads = self.loads()
        allowed, blocked = [], []
        for name, item in sorted(self.people.items()):
            verdict = self.check_placement(name, shift_name)
            row = {
                "employee": name,
                "hours": loads.get(name, 0.0),
                "roles": sorted(roles(item)),
                "is_shift_manager": bool(item.get("is_shift_manager")),
                "counts_toward_staffing": counts(item, self.profile),
                "closes_this_date": self.closes(item, slot),
            }
            if not verdict["ok"]:
                blocked.append(dict(row, reasons=verdict["blocked_by"]))
                continue
            allowed.append((
                candidate_key(
                    self.rows, slot, item, self.profile, loads.get(name, 0.0)
                ),
                dict(row, costs=verdict["costs"]),
            ))
        allowed.sort(key=lambda pair: pair[0])
        return {
            "shift": slot["shift_name"],
            "date": slot["slot_date"],
            "found": True,
            "still_missing": self.slot_state(slot)["missing"],
            "candidates": [item for _, item in allowed],
            # Named rather than silently dropped: "nobody legal is left" is
            # the sentence the manager needs when a shift stays short, and a
            # list that only ever shows who *can* work cannot produce it.
            "blocked": blocked,
        }

    def check_placement(self, employee: str, shift_name: str) -> dict:
        """What placing one person on one slot would mean. Changes nothing.

        `ok` is about usability, never about desirability: a row that would
        put somebody on their sixth straight day comes back `ok` with the
        cost attached, because refusing it here would be `audit.py` given the
        veto D3 spends its whole entry refusing to grant.
        """
        employee = text(employee)
        slot = self.slot(shift_name)
        blocked: List[dict] = []
        if slot is None:
            return _verdict(False, [{
                "code": "unknown_shift",
                "message": "אין משמרת בשם הזה בתאריך הזה",
            }], [])
        if employee not in self.people:
            return _verdict(False, [{
                "code": "unknown_employee",
                "message": "אין עובד/ת בשם הזה ברשימת הצוות",
            }], [])

        item = self.people[employee]
        if not eligible(item, slot["shift_name"]):
            blocked.append({
                "code": "not_eligible",
                "message": "%s אינו/ה כשיר/ה למשמרת %s"
                           % (employee, slot["shift_name"]),
            })
        if already_on(self.rows, employee, slot):
            blocked.append({
                "code": "already_assigned",
                "message": "%s כבר משובץ/ת למשמרת הזאת" % employee,
            })
        row = {
            "employee": employee,
            "shift": slot["shift_name"],
            "date": slot["slot_date"],
            "reason": "",
        }
        if hard_conflict(row, [slot], self.availability):
            blocked.append({
                "code": UNAVAILABLE,
                "message": "יש ל%s אילוץ קשיח בתאריך %s"
                           % (employee, slot["slot_date"]),
            })

        introduced = self.introduced(row)
        blocked.extend(
            {"code": item_["code"], "message": item_["message"]}
            for item_ in introduced if item_["code"] in BLOCKING_CODES
        )
        # A soft constraint arrives here as an ordinary cost: the manager
        # wrote it down as a preference, and overriding a preference is a
        # decision somebody is allowed to make as long as they say so.
        costs = [
            {"code": item_["code"], "message": item_["message"]}
            for item_ in introduced if item_["code"] in COST_CODES
        ]
        return _verdict(not blocked, blocked, costs)

    def workload(self) -> dict:
        """Hours per person over the history plus everything decided so far."""
        loads = self.loads()
        return {"date": self.day, "hours": [
            {"employee": name, "hours": loads.get(name, 0.0)}
            for name in sorted(self.people)
        ]}

    # -- the draft ---------------------------------------------------------

    def apply(self, rows: List[dict]) -> tuple:
        """Put the agent's rows into the draft. Returns (accepted, rejected).

        Not reachable through `run()`: the model names the four questions and
        nothing else, and what it decides arrives as its answer rather than
        as a tool that writes. A rejected row comes back carrying *why*, so
        the loop can hand the reason to the model instead of quietly dropping
        a decision it made.
        """
        accepted, rejected = [], []
        for raw in rows or []:
            # The date is this draft's, not the model's to state: a draft is
            # one date, and a row that had to name it could name the wrong
            # one. A row that does carry a date keeps it, so the same method
            # can take rows read back out of a schedule.
            row = assignment(
                dict(raw, date=date_text(raw.get("date")) or self.day)
            ) if isinstance(raw, dict) else None
            if row is None:
                rejected.append({
                    "row": raw if isinstance(raw, dict) else {},
                    "reason": "שורה חסרה עובד/ת, משמרת או תאריך",
                })
                continue
            if (row["shift"], row["date"]) not in self.keys:
                rejected.append({
                    "row": row,
                    "reason": "המשמרת הזאת אינה בתאריך שנבנה כרגע",
                })
                continue
            if not row["reason"]:
                # D8: an assignment nobody can account for is exactly what
                # the reason exists to prevent, and it is refused here as
                # well as by the repository.
                rejected.append({
                    "row": row, "reason": "שיבוץ בלי נימוק אינו נשמר",
                })
                continue
            verdict = self.check_placement(row["employee"], row["shift"])
            if not verdict["ok"]:
                rejected.append({
                    "row": row,
                    "reason": "; ".join(
                        item["message"] for item in verdict["blocked_by"]
                    ),
                })
                continue
            row["costs"] = verdict["costs"]
            self.rows.append(row)
            self._standing = None
            accepted.append(row)
        return accepted, rejected

    def reset(self, pinned: Optional[List[dict]] = None) -> None:
        """Take this date's rows back out, keeping the committed context.

        A repair turn re-answers the whole date, so the previous answer has
        to leave first — otherwise a corrected row lands beside the one it
        was correcting and the day ends up double-staffed. What the manager
        pinned goes back in: a re-answer is the agent's to redo, and the
        pins were never the agent's to begin with.
        """
        self.rows = [row for row in self.rows if not self.mine(row)]
        self.rows.extend(pinned or [])
        self._standing = None

    def assignments(self) -> List[dict]:
        """This date's rows — what a build persists."""
        return [row for row in self.rows if self.mine(row)]

    def mine(self, row: dict) -> bool:
        return (
            row.get("date") == self.day
            and (row.get("shift"), row.get("date")) in self.keys
        )

    def unfilled(self) -> List[dict]:
        """Slots still short, with what could still be done about them."""
        short = []
        for slot in self.slots:
            state = self.slot_state(slot)
            if state["missing"] <= 0:
                continue
            options = self.candidates(slot["shift_name"])
            short.append(dict(
                state,
                available=[
                    item["employee"] for item in options["candidates"]
                ],
            ))
        return short

    def standing(self) -> set:
        """The warnings the draft already carries, keyed. See `introduced`."""
        if self._standing is None:
            self._standing = _keyed(self.warnings_over(self.rows))
        return self._standing

    def warnings_over(self, rows: List[dict]) -> List[dict]:
        return audit(
            rows, self.shifts, self.employees, self.availability,
            self.profile, self.slots,
        )

    def warnings(self) -> List[dict]:
        """The audit over the draft, narrowed to this date."""
        return [
            row for row in self.warnings_over(self.rows)
            if row.get("date") in (None, "", self.day)
        ]

    # -- arithmetic --------------------------------------------------------

    def slot(self, shift_name: str) -> Optional[dict]:
        name = text(shift_name)
        return next(
            (slot for slot in self.slots if slot["shift_name"] == name), None
        )

    def loads(self) -> Dict[str, float]:
        return {
            row["employee"]: row["hours"]
            for row in load_history(
                self.history + self.rows, self.shifts, self.employees
            )
        }

    def closes(self, item: dict, slot: dict) -> bool:
        try:
            day = datetime.date.fromisoformat(slot["slot_date"])
        except (TypeError, ValueError):
            return False
        return rotation.holds(self.profile, item, day, slot["shift_name"])

    def introduced(self, row: dict) -> List[dict]:
        """The warnings this row would add — not the ones already standing.

        Diffed rather than filtered by name and date: a day that is already
        short does not become the fault of every person placed on it, and a
        candidate list that reported it that way would tell the agent every
        option is expensive.
        """
        before = self.standing()
        after = audit(
            self.rows + [row], self.shifts, self.employees, self.availability,
            self.profile, self.slots,
        )
        return [item for item in after if _key(item) not in before]

def _verdict(ok: bool, blocked: List[dict], costs: List[dict]) -> dict:
    return {
        "ok": bool(ok),
        # Never `True`, and stated rather than omitted: what code refuses
        # here is an unusable row, and the audit's findings stay advisory
        # (D3). The manager may still place by hand anything this reports.
        "blocking": False,
        "blocked_by": blocked,
        "costs": costs,
    }


def _keyed(warnings: List[dict]) -> set:
    return {_key(item) for item in warnings}


def _key(warning: dict) -> tuple:
    return (
        warning.get("code"), warning.get("employee"), warning.get("date"),
        warning.get("shift"), warning.get("message"),
    )


# -- the shared arithmetic, used by both engines ---------------------------


def required_rows(
    required_assignments: Optional[List[Any]],
    slots: List[dict],
    people: Dict[str, dict],
    availability: List[dict],
    day: str,
) -> List[dict]:
    """The manager's pins, refused loudly when one of them cannot stand.

    Raises rather than warning, unlike everything else here: a pin is the
    manager saying *this person, this shift*, and quietly dropping one would
    hand them back a schedule that silently disagrees with the instruction
    they just gave. Both engines validate pins through this, so the fallback
    cannot accept a row the agent's path refuses.
    """
    keys = {(slot["shift_name"], slot["slot_date"]) for slot in slots}
    rows = []
    for raw in required_assignments or []:
        row = assignment(raw)
        if row is None or (row["shift"], row["date"]) not in keys:
            continue
        if row["employee"] not in people:
            raise AgentError("עובד/ת בשיבוץ החובה לא נמצא/ה בצוות")
        if not eligible(people[row["employee"]], row["shift"]):
            raise AgentError(
                "%s אינו/ה כשיר/ה למשמרת %s"
                % (row["employee"], row["shift"])
            )
        if hard_conflict(row, slots, availability):
            raise AgentError(
                "שיבוץ החובה של %s ב-%s סותר אילוץ קשיח, סבב או תלתון"
                % (row["employee"], day)
            )
        row["reason"] = (
            text(raw.get("reason")) if isinstance(raw, dict) else ""
        ) or "שיבוץ חובה של המנהל"
        rows.append(row)
    return unique(rows)


def candidate_key(
    rows: List[dict], slot: dict, item: dict, profile: dict, hours: float,
) -> tuple:
    """How the code would rank one candidate for one slot.

    First minimise unmet mandatory capabilities, then prefer the closing
    group and finally the lightest accumulated load. Stable tie breakers make
    rerunning the same day produce the same order.
    """
    missing = missing_roles(rows, slot, profile)
    held = roles(item)
    manager_missing = bool(slot.get("requires_shift_manager")) and not any(
        person(profile, row["employee"]).get("is_shift_manager")
        for row in rows if same_slot(row, slot)
    )
    covers_roles = len(missing.intersection(held))
    covers_manager = manager_missing and bool(item.get("is_shift_manager"))
    try:
        day = datetime.date.fromisoformat(slot["slot_date"])
        closing = rotation.holds(profile, item, day, slot["shift_name"])
    except (TypeError, ValueError):
        closing = False
    remaining = len(missing) - covers_roles + int(
        manager_missing and not covers_manager
    )
    return (
        remaining, not covers_manager, -covers_roles, not closing,
        float(hours), text(item.get("name")),
    )


def reason_for(profile: dict, item: dict, slot: dict) -> str:
    """The sentence a code-made assignment carries (D8)."""
    try:
        day = datetime.date.fromisoformat(slot["slot_date"])
        closing = rotation.holds(profile, item, day, slot["shift_name"])
    except (TypeError, ValueError):
        closing = False
    if closing:
        group = text(item.get("rotation_group"))
        pattern = rotation.exit_pattern(profile, item)
        cycle = pattern if pattern in ("round", "triplet") else _cycle(
            profile, group
        )
        return "%s סוגר/ת במועד הזה; השיבוץ עומד במחזור המחייב." % (
            rotation.label(cycle, group) or "קבוצת הסגירה"
        )
    if slot.get("requires_shift_manager") and item.get("is_shift_manager"):
        return "שובץ/ה כמפקד/ת המשמרת, לפי זמינות ואיזון עומס."
    matched = sorted(missing_roles([], slot, profile).intersection(roles(item)))
    if matched:
        return "שובץ/ה לתפקיד %s, לפי זמינות ואיזון עומס." % ", ".join(matched)
    return "שובץ/ה לפי זמינות, כשירות ואיזון עומס."


def _cycle(profile: dict, group: str) -> str:
    if group == "ג":
        return "triplet"
    mode = text(((profile or {}).get("workplace") or {}).get("rotation_mode"))
    return mode if mode in ("round", "triplet") else "round"


def hard_conflict(
    row: dict, slots: List[dict], availability: List[dict]
) -> bool:
    """Whether a hard constraint stands against this row."""
    slot = next((item for item in slots if same_slot(row, item)), {})
    candidate = dict(
        row,
        start_time=slot.get("start_time"),
        end_time=slot.get("end_time"),
    )
    return any(
        item.get("is_hard", True) is not False
        and constraint_conflicts(candidate, item)
        for item in availability if isinstance(item, dict)
    )


def introduces_blocking(
    current: List[dict], row: dict, shifts: List[dict], staff: List[dict],
    availability: List[dict], profile: dict, slots: List[dict],
    codes: Optional[frozenset] = None,
) -> bool:
    """Whether adding this row raises a warning of a blocking kind."""
    codes = codes if codes is not None else BLOCKING_CODES
    warnings = audit(
        current + [row], shifts, staff, availability, profile, slots
    )
    return any(
        item.get("severity") == "warning"
        and item.get("code") in codes
        and item.get("date") in (None, "", row["date"])
        and item.get("employee") in (None, "", row["employee"])
        for item in warnings
    )


def legal_count(
    slot: dict, people: Dict[str, dict], availability: List[dict]
) -> int:
    """How many people could stand on this slot at all. Scarcity, in a number."""
    return sum(
        eligible(item, slot["shift_name"])
        and not hard_conflict({
            "employee": name,
            "shift": slot["shift_name"],
            "date": slot["slot_date"],
        }, [slot], availability)
        for name, item in people.items()
    )


def counted_on(
    rows: List[dict], slot: dict, people: Dict[str, dict], profile: dict
) -> int:
    return sum(
        same_slot(row, slot)
        and counts(people.get(row["employee"], {}), profile)
        for row in rows
    )


def missing_roles(rows: List[dict], slot: dict, profile: dict) -> set:
    present = set()
    for row in rows:
        if same_slot(row, slot):
            present.update(roles(person(profile, row["employee"])))
    return set(slot.get("required_roles") or []) - present


def roles(item: dict) -> set:
    held = item.get("roles")
    result = {text(role) for role in held if text(role)} if isinstance(
        held, list
    ) else set()
    role = text(item.get("role"))
    if role:
        result.add(role)
    return result


def counts(item: dict, profile: dict) -> bool:
    """Whether this person fills one of the slot's seats."""
    explicit = item.get("counts_toward_staffing")
    if isinstance(explicit, bool):
        return explicit
    if not item.get("is_trainee"):
        return True
    policy = (profile or {}).get("training_policy") or {}
    return bool(policy.get("counts_toward_staffing"))


def eligible(item: dict, shift: str) -> bool:
    allowed = item.get("eligible_shifts")
    return not isinstance(allowed, list) or not allowed or shift in allowed


def already_on(rows: List[dict], employee: str, slot: dict) -> bool:
    return any(
        row["employee"] == employee and same_slot(row, slot) for row in rows
    )


def same_slot(row: dict, slot: dict) -> bool:
    return (
        text(row.get("shift")) == text(
            slot.get("shift_name") or slot.get("shift")
        )
        and date_text(row.get("date")) == date_text(
            slot.get("slot_date") or slot.get("date")
        )
    )


def person(profile: dict, name: str) -> dict:
    return next(
        (row for row in employees(profile) if text(row.get("name")) == name),
        {},
    )


def employees(profile: dict) -> List[dict]:
    return [
        row for row in (profile or {}).get("employees") or []
        if isinstance(row, dict) and text(row.get("name"))
    ]


def assignment(raw: Any) -> Optional[dict]:
    """One row in the shape both engines and the repository speak."""
    if not isinstance(raw, dict):
        return None
    employee = text(raw.get("employee"))
    shift = text(raw.get("shift") or raw.get("shift_name"))
    date = date_text(raw.get("date") or raw.get("slot_date"))
    if not employee or not shift or not date:
        return None
    return {
        "employee": employee,
        "shift": shift,
        "date": date,
        "reason": text(raw.get("reason")),
    }


def unique(rows: List[dict]) -> List[dict]:
    result, seen = [], set()
    for row in rows:
        key = (row["employee"], row["shift"], row["date"])
        if key not in seen:
            seen.add(key)
            result.append(row)
    return result


def shift_hours(shifts: List[dict], name: str) -> float:
    shift = next(
        (
            row for row in shifts
            if isinstance(row, dict) and text(row.get("name")) == name
        ),
        {},
    )
    try:
        start = datetime.time.fromisoformat(text(shift.get("start_time")))
        end = datetime.time.fromisoformat(text(shift.get("end_time")))
    except ValueError:
        return 0.0
    minutes = (end.hour * 60 + end.minute) - (start.hour * 60 + start.minute)
    if minutes <= 0:
        minutes += 24 * 60
    weight = shift.get("hour_weight")
    weight = float(weight) if isinstance(weight, (int, float)) else 1.0
    return round(minutes / 60.0 * weight, 2)


def date_text(value: Any) -> str:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return text(value)


def text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


__all__ = [
    "BLOCKING_CODES",
    "COST_CODES",
    "DayDraft",
    "TOOL_CANDIDATES",
    "TOOL_CHECK_PLACEMENT",
    "TOOL_DESCRIPTIONS",
    "TOOL_NAMES",
    "TOOL_OPEN_SLOTS",
    "TOOL_WORKLOAD",
    "already_on",
    "assignment",
    "candidate_key",
    "counted_on",
    "counts",
    "date_text",
    "eligible",
    "employees",
    "hard_conflict",
    "introduces_blocking",
    "legal_count",
    "missing_roles",
    "person",
    "reason_for",
    "required_rows",
    "roles",
    "same_slot",
    "shift_hours",
    "text",
    "unique",
]
