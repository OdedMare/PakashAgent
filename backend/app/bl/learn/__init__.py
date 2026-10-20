"""What past schedules and past corrections say about how this workplace runs.

**Patterns are counted, never asked for** (D3): `observe_corrections()`
tallies the change log. **Rules are proposed
in the manager's own words** (D2): `RuleLearner` hands the counts to the model
and asks for sentences. **Nothing here is a rule until the manager says so**:
it returns *candidates* carrying their evidence, and gets no repository.

| Module | Owns |
|---|---|
| `corrections.py` | `observe_corrections()`: counting what the manager fixed |
| `learner.py` | `RuleLearner` and the candidate validation |
"""

from app.bl.learn.corrections import observe_corrections
from app.bl.learn.learner import CANDIDATE_SCHEMA, RuleLearner

__all__ = ["observe_corrections", "RuleLearner", "CANDIDATE_SCHEMA"]
