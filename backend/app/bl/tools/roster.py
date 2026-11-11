"""Which roster person a manager's word means -- or that it is unclear."""

from typing import List, Optional

from app.bl.tools.values import employees, text


def _result(found: bool, ambiguous: bool, matches: List[str],
            person: Optional[dict], roster: List[str]) -> dict:
    return {"found": found, "ambiguous": ambiguous, "matches": matches,
            "person": person, "roster": roster}


def resolve_employee(profile: dict, name: str) -> dict:
    """Which roster person a manager's word means — or that it is unclear.

    Exact match first, and an exact match wins outright: a workplace with
    both "דן" and "דניאל" must not have "דן" read as ambiguous. Only when
    nothing matches exactly does this fall back to a prefix and then a
    containment pass, and only there can the answer be *several* people --
    picking the first is the guess `changes.py` and `planner.py` are
    forbidden to make. Always a dict, never an exception.
    """
    wanted = text(name)
    people = employees(profile)
    roster = [text(row.get("name")) for row in people if text(row.get("name"))]
    if not wanted:
        return _result(False, False, [], None, roster)
    partial = (
        [p for p in people if text(p.get("name")) == wanted]
        or [p for p in people if text(p.get("name")).startswith(wanted)]
        or [p for p in people if wanted in text(p.get("name"))]
    )
    matches = [text(person.get("name")) for person in partial]
    if len(partial) == 1:
        return _result(True, False, matches, partial[0], roster)
    if len(partial) > 1:
        # Several real people, and no basis in the sentence for choosing.
        return _result(False, True, matches, None, roster)
    return _result(False, False, [], None, roster)


def find_person(profile: dict, name: str) -> Optional[dict]:
    """The one person this name means, or `None` when that is not one person."""
    return resolve_employee(profile, name)["person"]
