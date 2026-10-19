"""Answering a manager's question by running tools, with or without a model.

`ChangeAgent` handles the one-shot case by putting the whole period in front
of the model. That does not work for *"מי יכול להחליף את יוסי בסופ״ש"*, which
needs four countable things worked out in order. So this runs a **loop**: the
model picks tools, `bl/tools` answers with arithmetic, and the results go back
until the model can speak. It never contributes a number, a name, or a
verdict (D3).

**It answers; it does not act.** Every tool is read-only, this package holds
no repository, and the response schema has no operation in it — the same
shape `briefing.py` has (D15).

**Without a model it still works.** The fallback reads the sentence with
keyword matching (`bl/intent.py`), runs the *same tools*, and renders Hebrew
templates. The answer's content is identical either way, because the content
was never the model's to begin with.

| Module | Owns |
|---|---|
| `agent.py` | `PlanningAgent`: model first, fallback on failure |
| `model_loop.py` | The bounded tool loop |
| `fallback.py`, `fallback_answers.py` | The no-model path |
| `schema.py`, `shaping.py` | The response schema; bounding and payloads |
"""

from app.bl.planner.agent import PlanningAgent
from app.bl.planner.schema import PLANNER_RESPONSE_SCHEMA

__all__ = ["PlanningAgent", "PLANNER_RESPONSE_SCHEMA"]
