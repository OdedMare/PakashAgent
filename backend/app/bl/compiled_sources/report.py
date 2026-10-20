"""What code made of each standing source, for the setup screen to show.

One row per standing source the team has now, in the order setup lists
them. `status` is `compiled`, `unresolved` (with the reason; a binding one
sends builds to the full scheduler), or `pending` (not translated yet, or
not for today's roster). A read: nothing here translates or queues.
"""

from typing import List, Optional

from app.bl.compiled_sources.compiler import standing_sources
from app.bl.compiled_sources.keys import compiler_id, vocab_key
from app.common.time_context import israel_today

STATUS_PENDING = "pending"
_SUMMARY_FIELDS = ("availability", "required_assignments", "requests")


def report(repository, team_id: str, today: Optional[str] = None) -> List[dict]:
    if not hasattr(repository, "compiled_sources"):
        return []
    profile = repository.team_profile(team_id) or {}
    sources = standing_sources(repository, team_id, profile)
    rows = {row["source_key"]: row for row in repository.compiled_sources(
        team_id, vocab_key(profile), compiler_id(), [row["key"] for row in sources])}
    today = today or israel_today().isoformat()
    return [_line(source, rows.get(source["key"]), today) for source in sources]


def _line(source: dict, row: Optional[dict], today: str) -> dict:
    line = {key: source[key] for key in ("kind", "context", "text", "binding")}
    if row is None:
        return dict(line, status=STATUS_PENDING, reason="", question="", expires_on=None,
                    expired=False, items=0)
    expires = row.get("expires_on")
    translation = row.get("translation") or {}
    return dict(
        line, status=row["status"], reason=row.get("reason") or "",
        question=row.get("question") or "", expires_on=expires,
        expired=bool(expires) and expires < today,
        items=sum(len(translation.get(field) or []) for field in _SUMMARY_FIELDS),
    )


__all__ = ["STATUS_PENDING", "report"]
