"""A soldier's competence, raised, lowered or set from one sentence, no model.

"תעלה את הכשירות של יוסי", "תוריד כשירות לדנה", "הכשירות של רון מצטיינת":
the manager names people and either a level or a direction, and code can
read that with certainty. The plan is a `profile` turn handed to
`ChatPlanBuilder.prepare`, exactly what the model would return, so it waits
for the same approval. Anything this cannot read returns nothing and the
model takes the turn.

| Module | Owns |
|---|---|
| `reader.py` | The sentence: who, and which level or direction. Pure |
| `fast_path.py` | Turning a reading into a reply, a question or a pending plan |
"""

from app.bl.competence.fast_path import CompetenceFastPath
from app.bl.competence.reader import LABELS, LEVELS, read, shifted

__all__ = ["CompetenceFastPath", "LABELS", "LEVELS", "read", "shifted"]
