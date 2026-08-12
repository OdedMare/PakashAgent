"""Pull one JSON object out of a model reply.

Servers that are only approximately OpenAI-compatible wrap the object in a
markdown fence or in prose even when asked for JSON mode.
"""

import json
import re


def extract_json(text: str) -> dict:
    cleaned = _strip_fence(text.strip())
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        # Prose around the object: take the outermost braces and retry.
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end <= start:
            raise
        parsed = json.loads(cleaned[start:end + 1])
    if not isinstance(parsed, dict):
        raise json.JSONDecodeError("Expected a JSON object", cleaned, 0)
    return parsed


def _strip_fence(text: str) -> str:
    if not text.startswith("```"):
        return text
    text = re.sub(r"^```[A-Za-z]*\s*", "", text)
    return re.sub(r"```\s*$", "", text).strip()
