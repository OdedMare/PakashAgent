"""What a kept translation is keyed on, so that it is used only while true.

A translation answers "what does this sentence mean for code, given these
people and these shifts, as this compiler reads it". Each of the three is
part of the key: different words are a different source
(`scheduler.directives.source_key`), a roster change can make "דני"
ambiguous, and a changed prompt may read the same words differently.
"""

import hashlib
import json

from app.bl.prompts import load
from app.bl.shared import text

# Raise to throw away every kept translation, for a change in how code
# reads an answer that the prompt's own text does not show.
COMPILER_VERSION = "1"


def vocab_key(profile: dict) -> str:
    """The roster names and shift names a translation was checked against."""
    names = sorted({text(row.get("name")) for row in (profile or {}).get("employees") or []
                    if isinstance(row, dict) and text(row.get("name"))})
    shifts = sorted({text(row.get("name")) for row in (profile or {}).get("shifts") or []
                     if isinstance(row, dict) and text(row.get("name"))})
    return _digest(json.dumps([names, shifts], ensure_ascii=False))


def compiler_id() -> str:
    return "%s:%s" % (COMPILER_VERSION, _digest(load("scheduler_directives"))[:16])


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


__all__ = ["COMPILER_VERSION", "compiler_id", "vocab_key"]
