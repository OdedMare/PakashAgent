"""`RuleLearner`: counted patterns worded as rules the manager would recognise.

Stateless and handed no repository: it proposes, and the manager's approval
is what makes anything real (D7). Cell contents and the manager's stated
reasons reach the model as data to summarise, never as instruction.
"""

import json
from typing import Any, Optional

from app.bl.learn.values import bounded
from app.bl.prompts import load
from app.common.errors.errors import AgentError

_MAX_RULE_CHARS = 400
_CONFIDENCES = ("high", "medium", "low")

CANDIDATE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["rules", "notes"],
    "properties": {
        "rules": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["text", "kind", "evidence", "confidence"],
                "properties": {
                    # The manager's own language, because that is what a rule
                    # is in this product (D2).
                    "text": {"type": "string"},
                    "kind": {"type": "string", "enum": ["hard", "soft"]},
                    # What was counted, shown beside the rule so the manager
                    # approves a claim they can check.
                    "evidence": {"type": "string"},
                    "confidence": {"type": "string", "enum": list(_CONFIDENCES)},
                },
            },
        },
        "notes": {"type": "array", "items": {"type": "string"}},
    },
}


class RuleLearner(object):
    def __init__(self, llm):
        self._llm = llm

    def propose(
        self, observations: dict, profile: Optional[dict] = None,
        instructions: str = "",
    ) -> dict:
        """Candidate rules from patterns counted in files. Nothing is applied."""
        if not (observations or {}).get("people"):
            return {"rules": [], "notes": []}
        return self._ask("learn", {
            "observations": observations,
            "profile": _profile_for_model(profile),
            "instructions": bounded(instructions),
        })

    def propose_from_corrections(
        self, corrections: dict, profile: Optional[dict] = None,
    ) -> dict:
        """Candidate rules from what the manager kept overriding.

        Same contract as `propose()`. Returns early on too little history: a
        round trip to be told there is nothing yet is computable here.
        """
        if not (corrections or {}).get("repeated"):
            return {"rules": [], "notes": []}
        return self._ask("learn_changes", {
            "corrections": corrections,
            "profile": _profile_for_model(profile),
        })

    def _ask(self, prompt: str, payload: dict) -> dict:
        answer = self._llm.complete_json(
            load(prompt),
            json.dumps(payload, ensure_ascii=False),
            schema=CANDIDATE_SCHEMA,
            flow="learn",
        )
        return candidates(answer)


def candidates(answer: Any) -> dict:
    """Validate and normalise what the model returned.

    Shared by both paths so they cannot drift: a candidate without evidence is
    dropped (approving an uncheckable rule would make the confirm step
    theatre), anything but an explicit `hard` is soft (an invented hard rule
    nags the manager, D1), and `approved` is always false (D7).
    """
    if not isinstance(answer, dict):
        raise AgentError("המודל החזיר תשובה לא תקינה")
    rules = [rule for rule in map(_rule, answer.get("rules") or []) if rule]
    notes = [bounded(note, _MAX_RULE_CHARS) for note in answer.get("notes") or []]
    return {"rules": rules, "notes": [note for note in notes if note]}


def _rule(item: Any) -> Optional[dict]:
    if not isinstance(item, dict):
        return None
    text = bounded(item.get("text"), _MAX_RULE_CHARS)
    evidence = bounded(item.get("evidence"), _MAX_RULE_CHARS)
    if not text or not evidence:
        return None
    confidence = item.get("confidence")
    return {
        "text": text,
        "kind": "hard" if item.get("kind") == "hard" else "soft",
        "evidence": evidence,
        "confidence": confidence if confidence in _CONFIDENCES else "low",
        # Never approved by the act of being proposed.
        "approved": False,
    }


def _profile_for_model(profile: Optional[dict]) -> dict:
    """The workplace, trimmed to what rule-writing needs."""
    profile = profile if isinstance(profile, dict) else {}
    return {
        "workplace": bounded(profile.get("workplace")),
        "shifts": profile.get("shifts") or [],
        "employees": profile.get("employees") or [],
        # So the model does not propose a rule already stated.
        "existing_rules": profile.get("rules") or [],
    }
