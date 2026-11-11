"""An absence, from one sentence to a plan, with no model call.

**Pure Python.** Reading *"עודד חולה בשני ושלישי"*, finding his shifts and
the people free to cover them is a lookup and arithmetic, so it is code's
([D3](../../../../docs/DECISIONS.md#d3--the-agent-decides-code-only-audits-)).
Doing it here takes the commonest manager request off the model loop.

**It writes nothing.** The plan it builds goes through
`ChatPlanBuilder.prepare` -- the model's own checks and audit -- and waits
for the manager's approval like any other. Anything it cannot read with
certainty is left to the model, unchanged.

| Module | Owns |
|---|---|
| `dates.py` | Every date a sentence names: lists, ranges, weekdays, the week |
| `reader.py` | Whether a sentence reports one person's absence, and what to do next |
| `selections.py` | The manager's chosen replacement, as the candidate buttons word it |
| `options.py` | Ranked candidates per shift and a fair pick across the whole absence |
| `replies.py` | The Hebrew the path says |
| `fast_path.py` | Finishing a chat turn in code, or declining it untouched |
"""

from app.bl.absence.fast_path import AbsenceFastPath
from app.bl.absence.options import AbsenceOptions
from app.bl.absence.selections import selection_sentence

__all__ = ["AbsenceFastPath", "AbsenceOptions", "selection_sentence"]
