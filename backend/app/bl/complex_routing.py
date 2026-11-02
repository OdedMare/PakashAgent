"""Which משמרות of a מכלול a commander's sentence is about (D43).

The commander's chat speaks to every משמרת, but each משמרת keeps its own
agent, roster, rules and solver -- so a sentence is sent to the agents it
concerns, and each prepares its own plan, approved on its own. Deciding
which is reading, not judging, and is done here with no model, the way
`bl/intent/` reads a sentence: by the מכלול's own words.

- A משמרת named in the sentence is addressed ("במשמרת ב'…").
- Otherwise a soldier named in it addresses their own משמרת -- the
  sentence is about them, and only their משמרת can move them.
- A sentence naming neither is about the whole מכלול ("מי חסר השבוע?"),
  and goes to every משמרת.

It never guesses between two readings: a name two משמרות share addresses
both, and each agent asks its own question if it must.
"""

import re
from typing import Dict, Iterable, List

_PARTICLES = "ובלמשהכ"
_PREFIXES = [""] + list(_PARTICLES) + [a + b for a in _PARTICLES for b in _PARTICLES]
_PUNCTUATION = re.compile(r"[\"'׳״`.,:;!?()\[\]{}\-–—/\\]+")


def _words(text: str) -> str:
    """The sentence as space-separated words, padded, for whole-word search."""
    return " %s " % " ".join(_PUNCTUATION.sub(" ", text or "").split())


def _says(words: str, name: str) -> bool:
    phrase = _words(name).strip()
    if not phrase:
        return False
    # Hebrew glues up to two particles to the word after it: "במשמרת",
    # "לדנה", "ולמשמרת".
    return any((" %s%s " % (prefix, phrase)) in words for prefix in _PREFIXES)


def _team_names(name: str) -> Iterable[str]:
    """A משמרת's name, and its name without the word "משמרת" -- a commander
    says "ב'" or "צוות ב" as often as the full "משמרת ב'"."""
    yield name
    bare = re.sub(r"^\s*(משמרת|צוות)\s+", "", name or "").strip()
    if bare and bare != name and len(_words(bare).strip()) > 1:
        yield bare


def _what_people_are_called(teams: List[Dict]) -> Dict[str, List[str]]:
    """Each soldier's full name, and their first name when nobody else in
    the מכלול shares it -- "דנה" is a person only if there is one Dana."""
    firsts: Dict[str, int] = {}
    for team in teams:
        for person in team.get("employees", []):
            first = (person or "").split()[0] if (person or "").split() else ""
            firsts[first] = firsts.get(first, 0) + 1
    calls = {}
    for team in teams:
        for person in team.get("employees", []):
            parts = (person or "").split()
            calls[person] = [person] + (
                [parts[0]] if len(parts) > 1 and firsts.get(parts[0]) == 1 else [])
    return calls


def route(content: str, teams: List[Dict]) -> Dict:
    """`teams` are `{id, name, employees: [names]}`; returns the ids the
    sentence addresses and why, in the commander's words."""
    words = _words(content)
    named = [team["id"] for team in teams
             if any(_says(words, name) for name in _team_names(team["name"]))]
    if named:
        return {"team_ids": named, "by": "team"}
    calls = _what_people_are_called(teams)
    people = [team["id"] for team in teams
              if any(_says(words, name)
                     for person in team.get("employees", [])
                     for name in calls.get(person, [person]))]
    if people:
        return {"team_ids": people, "by": "soldier"}
    return {"team_ids": [team["id"] for team in teams], "by": "all"}


__all__ = ["route"]
