"""Reading a manager's sentence without a model.

**Pure Python. No LLM call, ever.** This is the floor the product stands on
when no model is configured, when the model is down, and when it is too slow
to wait for — and `README.md`'s promise that the product works without an LLM
is the reason it exists.

## What this is and is not

It is **not** a second `ChangeAgent`. It does not decide who should replace
whom, it does not write Hebrew explanations of its judgment, and it never
produces an operation to apply. What it does is far smaller and entirely
mechanical: given *"מי יכול להחליף את יוסי בשבת"*, work out that the manager
is asking for **replacements**, that the person is **יוסי**, and that the day
is **Saturday** — then hand those to `bl/tools.py`, which answers with
arithmetic.

That split is the same one running through the whole codebase
([D3](../../../docs/DECISIONS.md#d3--the-agent-decides-code-only-audits-)):
the model is for judgment and phrasing, code is for counting. Matching a
handful of Hebrew keywords against a roster the workspace already declared is
not judgment. It is a lookup, and a lookup is something code can do honestly.

**What is lost without the model is real and is not hidden.** A deterministic
read of a sentence handles the shapes below and nothing else; anything it
cannot place comes back as `INTENT_UNKNOWN` and the caller says plainly that
it did not understand, rather than guessing. Guessing is the failure this
module must not have: an agent that acts on a misread sentence with no model
to blame is worse than one that asks.

## The shapes it reads

- **replacements** — *"מי יכול להחליף את X"*, *"מחליף ל-X"*
- **absence** — *"X חולה ביום חמישי"*, *"X בחופש"* — read as a request for
  replacements for that person on that day, because that is what a manager
  saying it wants next.
- **gaps** — *"מה חסר"*, *"איפה חסרים אנשים"*, *"משמרות ריקות"*
- **employee** — *"מה יש ל-X"*, *"כמה שעות יש ל-X"*
- **publish readiness** — *"מה חסר לפני פרסום"*, *"אפשר לפרסם"*
- **period** — *"מה יש השבוע"*, *"תראה לי את השבוע"*

Names come from the roster, never from the sentence's own shape: a token is
an employee because the workplace declared it, which is what stops a
misspelled word from becoming a person. Dates come from Hebrew weekday names
and from `היום`/`מחר`/`אתמול`, resolved against the period being asked about
rather than against the server's clock where a period is known.
"""

from app.bl.intent.reader import read
from app.bl.intent.vocabulary import (
    INTENT_ABSENCE,
    INTENT_EMPLOYEE,
    INTENT_GAPS,
    INTENT_PERIOD,
    INTENT_PUBLISH,
    INTENT_REPLACEMENTS,
    INTENT_TEAM,
    INTENT_UNKNOWN,
)

__all__ = [
    "read", "INTENT_REPLACEMENTS", "INTENT_ABSENCE", "INTENT_GAPS",
    "INTENT_EMPLOYEE", "INTENT_PUBLISH", "INTENT_PERIOD", "INTENT_TEAM",
    "INTENT_UNKNOWN",
]
