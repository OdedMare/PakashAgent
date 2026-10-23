"""The manager's choice of replacement, as the candidate buttons write it.

Both the chat's candidate cards and the replacement tab send one sentence
per chosen slot: *"אני בוחר את יוסי למשמרת בוקר בתאריך 2026-10-05 במקום
דנה."* The words are the manager's choice and are kept in the transcript;
this reads them back so the plan can be assembled without a model round.
Names and shifts are checked against the roster and the vocabulary by the
caller, never trusted from the text.
"""

import re
from typing import List

_SELECTION = re.compile(
    r"(?:אני\s+)?בוחר(?:ת)?\s+(?:את\s+)?(?P<employee>[^\n.;]+?)\s+למשמרת\s+"
    r"(?P<shift>[^\n.;]+?)\s+בתאריך\s+(?P<date>\d{4}-\d{2}-\d{2})"
    r"(?:\s+במקום\s+(?P<replacing>[^\n.;]+?))?\s*(?:[.;\n]|$)"
)


def selections(text: str) -> List[dict]:
    """Every `{employee, shift, date, replacing}` the sentence chooses."""
    return [
        {key: (match.group(key) or "").strip()
         for key in ("employee", "shift", "date", "replacing")}
        for match in _SELECTION.finditer(text or "")
    ]


def strip_selections(text: str) -> str:
    """The sentence with its choices taken out, for reading who is absent:
    a chosen replacement is a name too, and must not count as a second
    person the absence could be about."""
    return _SELECTION.sub(" ", text or "").strip()


def selection_sentence(employee: str, shift: str, date: str, replacing: str = "") -> str:
    """The one wording every surface sends, so one reader parses them all."""
    tail = " במקום %s" % replacing if replacing else ""
    return "אני בוחר את %s למשמרת %s בתאריך %s%s." % (employee, shift, date, tail)
