"""Conversational edits to a live schedule.

The step-4 loop: *"דנה חולה ביום חמישי."*

1. Parse the request.
2. **If the manager gave no reason, ask for one** (D8) — asked for rather
   than rejected, because an omission is not an error.
3. Propose a replacement **with the agent's justification**.
4. On confirmation: `schedule_service` applies it and appends to the log.

This package proposes. It does not write — it is handed no repository, which
is what keeps "the agent decided" and "the manager agreed" as two separate,
auditable events.

| Module | Owns |
|---|---|
| `agent.py` | `ChangeAgent`: the payload and the model call |
| `proposal.py` | The two gates (reason, target), enforced in code |
| `targets.py` | Bounding operations to targets the schedule has |
| `questions.py` | The one question or report a held proposal carries |
| `profile_ops.py` | Profile edits and implied constraints |
| `schema.py` | The operation vocabulary and response schema |
"""

from app.bl.changes.agent import ChangeAgent
from app.bl.changes.schema import (
    CHANGE_RESPONSE_SCHEMA,
    OP_ASSIGN,
    OP_REMOVE,
    OP_SWAP,
    PROFILE_ADD_EMPLOYEE,
    PROFILE_ADD_SHIFT,
    PROFILE_UPDATE_EMPLOYEE,
    PROFILE_UPDATE_SHIFT,
)

__all__ = [
    "ChangeAgent", "CHANGE_RESPONSE_SCHEMA",
    "OP_ASSIGN", "OP_REMOVE", "OP_SWAP",
    "PROFILE_ADD_EMPLOYEE", "PROFILE_UPDATE_EMPLOYEE",
    "PROFILE_ADD_SHIFT", "PROFILE_UPDATE_SHIFT",
]
