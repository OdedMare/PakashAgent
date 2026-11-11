"""Translate the manager's words into what the solver can honour.

A bounded tool loop: the model may resolve names, list slots, read a
person's eligibility, check a draft and dry-run it before answering, and
code validates the final answer exactly as the single-call translation
always did. Pure Python tools, no repository, nothing written.

| Module | Owns |
|---|---|
| `agent.py` | `DirectiveAgent`: the loop and its bounds |
| `tools.py` | `TranslationTools`: the five read-only tools |
| `partial.py` | Per-source outcomes: kept whole or left out whole, and reported |
| `schema.py` | One turn's shape, the tool names and their descriptions |
"""

from app.bl.directive_agent.agent import MAX_TURNS, DirectiveAgent

__all__ = ["DirectiveAgent", "MAX_TURNS"]
