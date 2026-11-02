"""The agent: one saved conversation per manager (`docs/MANAGER_CHAT.md`).

A turn prepares a plan and writes nothing; `apply.py` applies it on the
manager's approval, atomically, after checking nothing moved.

| Module | Owns |
|---|---|
| `service.py` | `ManagerChatService`: the conversation, its turns as jobs, approval and discard |
| `reply.py` | One turn: the zero-model fast path, then the model rounds and their read-only tools |
| `fast.py` | The zero-model answers run before any model round (`bl/absence/`, D36) |
| `tools.py` | The chat's own read-only tools and conversation context |
| `state.py` | What a turn starts from, serialised slowest-changing first; `schedule_for_chat` |
| `schema.py` | The reply's JSON schema and the suggestion chips |
| `contract.py` | The plan contract: normalising a turn, auditing a plan, its fingerprint |
| `planner.py` | `ChatPlanBuilder`: validating and auditing the plan the model proposed |
| `vacancies.py` | Filling the seats a planned removal leaves with the solver (D40) |
| `generation.py` | A generation preview through the solver |
| `lifecycle.py` | Departures, blank periods and shift-grid migrations, prepared read-only |
| `constraints.py` | Profile and constraint edits: normalising, impact, affected periods |
| `management.py` | Inbox and preference actions, prepared read-only and applied on approval |
| `apply.py` | `ChatPlanApplier`: one transaction on approval, after a state check |
| `draft.py` | Saving the reply as it streams |

`ManagerChatService` is loaded on first use rather than here: `bl/absence/`
imports `contract.py`, and the service imports `bl/absence/`, so importing
it eagerly would make importing either package a cycle.
"""

__all__ = ["ManagerChatService"]


def __getattr__(name):
    if name == "ManagerChatService":
        from app.bl.chat.service import ManagerChatService
        return ManagerChatService
    raise AttributeError("module %r has no attribute %r" % (__name__, name))
