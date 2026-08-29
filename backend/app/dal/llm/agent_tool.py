"""Small boundary between business tools and the OpenAI Agents SDK."""

from dataclasses import dataclass
from typing import Any, Callable, Dict


@dataclass(frozen=True)
class AgentTool:
    """One deterministic function the SDK-managed agent may call."""

    name: str
    description: str
    parameters: Dict[str, Any]
    invoke: Callable[[dict], Any]
    strict: bool = False


__all__ = ["AgentTool"]
