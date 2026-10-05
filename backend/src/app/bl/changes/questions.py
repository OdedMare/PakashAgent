"""What the agent says when a proposal is held: one question, or one report.

One line about one target each time: a manager handed three questions answers
none of them, and resolving the first commonly resolves the rest.
"""

from typing import List

from app.bl.changes.targets import NOT_ASSIGNED
from app.bl.changes.values import bounded
from app.bl.tools import resolve_employee


def unresolved_people(operations: List[dict], profile: dict) -> List[dict]:
    """Every person an operation names whom the roster cannot pin down.

    A name matching *several* people needs "which one", and a name matching
    *none* needs "who did you mean". Both are the model having supplied an
    identity rather than read one.
    """
    unresolved, seen = [], set()
    for operation in operations:
        for field in ("employee", "with_employee"):
            name = bounded(operation.get(field))
            if not name or name in seen:
                continue
            seen.add(name)
            found = resolve_employee(profile, name)
            if not found["found"]:
                unresolved.append({
                    "name": name,
                    "ambiguous": bool(found["ambiguous"]),
                    "matches": found["matches"],
                })
    return unresolved


def ask_which_person(unresolved: List[dict]) -> str:
    first = unresolved[0]
    if first["ambiguous"] and first["matches"]:
        return "יש כמה עובדים בשם %s — למי מהם התכוונתם: %s?" % (
            first["name"], "‏, ".join(first["matches"]),
        )
    return (
        "לא זיהיתי מי זה/זו %s ברשימת הצוות. אפשר לכתוב את השם כפי שהוא "
        "מופיע ברשימה?" % first["name"]
    )


def ask_which_shift(held: dict) -> str:
    """Offers the real candidates rather than asking an open question."""
    options = held.get("options") or []
    if options:
        return "לאיזו משמרת ב-%s התכוונת עבור %s — %s?" % (
            held["date"], held["employee"], " או ".join(options),
        )
    return "לאיזו משמרת ב-%s התכוונת עבור %s?" % (held["date"], held["employee"])


def report_dropped(dropped: List[dict]) -> str:
    """What could not be carried out, said plainly instead of swallowed."""
    first = dropped[0]
    if first["why"] == NOT_ASSIGNED:
        return (
            "%s לא משובץ/ת ב-%s בסידור הזה, אז אין מה להוריד. אפשר לבדוק את "
            "התאריך?" % (first["employee"], first["date"])
        )
    if first["shift"]:
        return (
            "אין משמרת %s בתאריך %s בסידור הזה, אז לא ביצעתי כלום. אפשר "
            "לבדוק את המשמרת ואת התאריך?" % (first["shift"], first["date"])
        )
    return (
        "אין משמרות בתאריך %s בסידור הזה, אז לא ביצעתי כלום. אפשר לבדוק את "
        "התאריך?" % first["date"]
    )
