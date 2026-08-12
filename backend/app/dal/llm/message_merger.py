"""Fold the system prompt into the user turn.

The last rung of the degradation ladder: some local deployments reject a
`system` role outright, so the same content is delivered as one user message.
"""

from typing import List


def merge_system_into_user(messages: List[dict]) -> List[dict]:
    system = [item["content"] for item in messages if item["role"] == "system"]
    rest = [item for item in messages if item["role"] != "system"]
    if not system or not rest:
        return rest or messages
    merged = dict(rest[0])
    merged["content"] = "\n\n".join(system + [merged["content"]])
    return [merged] + rest[1:]
