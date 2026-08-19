"""What a stack of past schedules says about how this workplace actually runs.

The manager uploads every file they have — the last year of `.xlsx` and
`.docx` sheets — and the product reads *history* out of them rather than just
rows. Two different things come out, and they are separated here on purpose:

**Patterns are counted, never asked for.** "יערה worked 14 of the last 16
mornings and no evenings" is arithmetic over the imported assignments, and
arithmetic is code's job
([D3](../../../docs/DECISIONS.md#d3--the-agent-decides-code-only-audits-)).
A model asked to tally would get it subtly wrong, and a wrong tally is worse
than none because it reads as authoritative. `observe()` does the counting.

**Rules are proposed in the manager's own words.** Turning "never worked a
Friday evening" into a sentence the manager recognises is writing, and the
rules this product keeps are natural-language
([D2](../../../docs/DECISIONS.md#d2--rules-stay-natural-language)) — there is
no structured rule vocabulary to compile into. `propose()` hands the counted
patterns to the model and asks for sentences.

**Nothing here is a rule until the manager says so.** A pattern is evidence,
and the leap from "has not happened" to "must not happen" is exactly the one
a person has to make: a file showing nobody on Saturday may mean Saturday is
closed, or may mean the sheet only covered weekdays. So this returns
*candidates* carrying their evidence, and D7's confirm step is where they
become rules. That is also why this module gets no repository.

The imported files are the least trusted input the product handles — they are
arbitrary spreadsheets, and a cell can contain any text at all. Cell contents
reach the model as data to summarise, never as instruction.
"""

import datetime
import json
from typing import Any, Dict, List, Optional

from app.bl.prompts import load
from app.common.errors import AgentError

# Enough history to see a pattern, bounded because every row is counted
# several times and the tallies are what reach the model.
_MAX_ASSIGNMENTS = 5000
_MAX_TEXT_CHARS = 2000

# A person must appear this many times before their record is read as a
# pattern at all. Below it the sample is too small to mean anything, and a
# confident claim from three shifts is how a product loses the manager's
# trust on the first screen.
_MIN_OBSERVATIONS = 4

# How lopsided a split has to be before it is worth mentioning. 0.9 rather
# than 1.0 because a real rota has exceptions -- somebody covered one evening
# once -- and demanding a perfect record would hide every true pattern.
_DOMINANT = 0.9
# The mirror: a shift someone has essentially never worked.
_ABSENT = 0.02

_HEBREW_WEEKDAYS = (
    "יום שני", "יום שלישי", "יום רביעי", "יום חמישי",
    "יום שישי", "שבת", "יום ראשון",
)

CANDIDATE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["rules", "notes"],
    "properties": {
        "rules": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["text", "kind", "evidence", "confidence"],
                "properties": {
                    # The manager's own language, because that is what a rule
                    # is in this product (D2).
                    "text": {"type": "string"},
                    "kind": {"type": "string", "enum": ["hard", "soft"]},
                    # What was counted. Shown beside the rule so the manager
                    # approves a claim they can check, not a claim they must
                    # take on faith.
                    "evidence": {"type": "string"},
                    "confidence": {
                        "type": "string", "enum": ["high", "medium", "low"],
                    },
                },
            },
        },
        "notes": {"type": "array", "items": {"type": "string"}},
    },
}


def observe(
    assignments: List[dict],
    unavailability: Optional[List[dict]] = None,
    profile: Optional[dict] = None,
) -> dict:
    """Countable facts across every imported period. No model call.

    Returns per-person tallies, the shift and weekday splits, and the pairs
    of people who appear together — everything a rule could be founded on,
    computed rather than inferred.
    """
    rows = _bounded_rows(assignments, _MAX_ASSIGNMENTS)
    shifts = _declared_shifts(profile)

    people: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        name = _text(row.get("employee"))
        shift_name = _text(row.get("shift"))
        date = _date(row.get("date"))
        if not name or not date:
            continue
        record = people.setdefault(name, {
            "total": 0, "shifts": {}, "weekdays": {},
            "first_seen": date, "last_seen": date,
        })
        record["total"] += 1
        record["shifts"][shift_name] = record["shifts"].get(shift_name, 0) + 1
        weekday = _HEBREW_WEEKDAYS[date.weekday()]
        record["weekdays"][weekday] = record["weekdays"].get(weekday, 0) + 1
        record["first_seen"] = min(record["first_seen"], date)
        record["last_seen"] = max(record["last_seen"], date)

    return {
        "periods": _period(rows),
        "people": _per_person(people, shifts),
        "coverage": _coverage(rows),
        "stated_unavailability": _stated(unavailability),
        "totals": {
            "assignments": len(rows),
            "people": len(people),
            "shifts": sorted({
                _text(row.get("shift")) for row in rows if _text(row.get("shift"))
            }),
        },
    }


def _per_person(
    people: Dict[str, Dict[str, Any]], shifts: List[str]
) -> List[dict]:
    """Each person's record, with the lopsided splits already identified.

    The dominance test runs here rather than in the prompt because it is a
    ratio, and which side of a threshold a ratio falls on is not a judgment
    call — it is the arithmetic the model is explicitly not trusted with.
    """
    found = []
    for name in sorted(people):
        record = people[name]
        total = record["total"]
        always, never = [], []
        if total >= _MIN_OBSERVATIONS:
            # `shifts` is the declared vocabulary, so a shift the person has
            # never worked is visible as a zero. Counting only what appears
            # in their rows would make "never works evenings" unrepresentable
            # -- the absence is the whole signal.
            for shift_name in shifts or list(record["shifts"]):
                count = record["shifts"].get(shift_name, 0)
                share = float(count) / total
                if share >= _DOMINANT:
                    always.append(shift_name)
                elif share <= _ABSENT:
                    never.append(shift_name)
        found.append({
            "employee": name,
            "assignments": total,
            "by_shift": record["shifts"],
            "by_weekday": record["weekdays"],
            "always": always,
            "never": never,
            "first_seen": record["first_seen"].isoformat(),
            "last_seen": record["last_seen"].isoformat(),
            # Below the floor nothing is claimed, and the reason is stated so
            # the model does not fill the silence with a guess.
            "enough_data": total >= _MIN_OBSERVATIONS,
        })
    return found


def _coverage(rows: List[dict]) -> dict:
    """Which weekdays and shifts the history covers at all.

    A weekday with no rows anywhere is the ambiguous case that matters most:
    it may be a closed day or merely a day the sheets never included, and
    those two mean opposite things. Reported as a fact so the model can say
    which it cannot tell.
    """
    weekdays: Dict[str, int] = {}
    per_shift: Dict[str, int] = {}
    for row in rows:
        date = _date(row.get("date"))
        if date is None:
            continue
        weekday = _HEBREW_WEEKDAYS[date.weekday()]
        weekdays[weekday] = weekdays.get(weekday, 0) + 1
        shift_name = _text(row.get("shift"))
        if shift_name:
            per_shift[shift_name] = per_shift.get(shift_name, 0) + 1
    return {
        "by_weekday": weekdays,
        "by_shift": per_shift,
        "weekdays_never_seen": [
            day for day in _HEBREW_WEEKDAYS if day not in weekdays
        ],
    }


def _stated(unavailability: Optional[List[dict]]) -> List[dict]:
    """Constraints the files stated outright, which are not inferences.

    A `לא זמינה` cell is the manager already having written the constraint
    down. It is evidence of a completely different quality from a counted
    absence, so it travels separately and is never blended into a pattern.
    """
    found = []
    for row in _bounded_rows(unavailability, _MAX_ASSIGNMENTS):
        employee = _text(row.get("employee"))
        date = _date(row.get("date"))
        if not date:
            continue
        found.append({
            "employee": employee,
            "date": date.isoformat(),
            "shift": _text(row.get("shift")),
            "reason": _text(row.get("reason")),
        })
    return found


def _period(rows: List[dict]) -> dict:
    dates = [_date(row.get("date")) for row in rows]
    dates = sorted(day for day in dates if day is not None)
    if not dates:
        return {"starts_on": "", "ends_on": "", "days": 0}
    return {
        "starts_on": dates[0].isoformat(),
        "ends_on": dates[-1].isoformat(),
        "days": (dates[-1] - dates[0]).days + 1,
    }


class RuleLearner(object):
    """Counted patterns turned into rules the manager would recognise.

    Stateless and handed no repository: it proposes, and the manager's
    approval is what makes anything real (D7).
    """

    def __init__(self, llm):
        self._llm = llm

    def propose(
        self,
        observations: dict,
        profile: Optional[dict] = None,
        instructions: str = "",
    ) -> dict:
        """Candidate rules with their evidence. Nothing is applied.

        The tallies go in as facts; what comes back is wording. Every
        candidate is dropped unless it carries both text and evidence — a
        rule the manager cannot check is one they cannot meaningfully
        approve, which would make the confirm step theatre.
        """
        if not (observations or {}).get("people"):
            return {"rules": [], "notes": []}

        answer = self._llm.complete_json(
            load("learn"),
            json.dumps({
                "observations": observations,
                "profile": _profile_for_model(profile),
                "instructions": _bounded(instructions),
            }, ensure_ascii=False),
            schema=CANDIDATE_SCHEMA,
        )
        if not isinstance(answer, dict):
            raise AgentError("המודל החזיר תשובה לא תקינה")

        rules = []
        for item in answer.get("rules") or []:
            if not isinstance(item, dict):
                continue
            text = _bounded(item.get("text"), 400)
            evidence = _bounded(item.get("evidence"), 400)
            if not text or not evidence:
                continue
            kind = item.get("kind")
            rules.append({
                "text": text,
                # Anything but an explicit `hard` is soft. A rule wrongly
                # marked hard is the expensive direction: D1 makes hard rules
                # strong instructions plus a loud warning, so an invented one
                # would nag the manager about a rule they never stated.
                "kind": "hard" if kind == "hard" else "soft",
                "evidence": evidence,
                "confidence": (
                    item.get("confidence")
                    if item.get("confidence") in ("high", "medium", "low")
                    else "low"
                ),
                # Never approved by the act of being proposed.
                "approved": False,
            })
        return {
            "rules": rules,
            "notes": [
                _bounded(note, 400)
                for note in (answer.get("notes") or [])
                if _bounded(note, 400)
            ],
        }


def _profile_for_model(profile: Optional[dict]) -> dict:
    """The workplace, trimmed to what rule-writing needs."""
    profile = profile if isinstance(profile, dict) else {}
    return {
        "workplace": _bounded(profile.get("workplace")),
        "shifts": profile.get("shifts") or [],
        "employees": profile.get("employees") or [],
        # The rules already recorded, so the model does not propose one the
        # manager has stated in their own words already.
        "existing_rules": profile.get("rules") or [],
    }


def _declared_shifts(profile: Optional[dict]) -> List[str]:
    shifts = (profile or {}).get("shifts") or []
    names = []
    for shift in shifts:
        name = _text(shift.get("name")) if isinstance(shift, dict) else _text(shift)
        if name and name not in names:
            names.append(name)
    return names


def _bounded_rows(rows: Any, limit: int) -> List[dict]:
    if not isinstance(rows, list):
        return []
    return [row for row in rows[:limit] if isinstance(row, dict)]


def _bounded(value: Any, limit: int = _MAX_TEXT_CHARS) -> str:
    text = value.strip() if isinstance(value, str) else ""
    return text[:limit]


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _date(value: Any) -> Optional[datetime.date]:
    if isinstance(value, datetime.date) and not isinstance(value, datetime.datetime):
        return value
    if isinstance(value, datetime.datetime):
        return value.date()
    try:
        return datetime.datetime.strptime(_text(value)[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


__all__ = ["observe", "RuleLearner", "CANDIDATE_SCHEMA"]
