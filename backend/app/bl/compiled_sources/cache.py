"""`TranslationCache`: one team's kept translations, behind a port.

The scheduler and the translating agent hold no repository (D19), so the
cache is what they are handed: bound to one team, it reads and writes
`compiled_sources` and `source_anchors` and nothing else. `NullCache` is the
same port keeping nothing, for callers with no team and for tests.

Only standing sources (`persistent`) are ever looked up or kept; this
build's own instruction is translated every time.
"""

from typing import Dict, List, Optional

from app.bl.compiled_sources.keys import compiler_id, vocab_key
from app.bl.compiled_sources.shape import to_outcome, to_row
from app.common.time_context import israel_today


class NullCache:
    def __init__(self, today: Optional[str] = None):
        self._today = today

    def today(self) -> str:
        return self._today or israel_today().isoformat()

    def anchors(self, sources: List[dict]) -> Dict[str, str]:
        """The date each standing source was first seen: what "3 days" counts from."""
        return {row["id"]: self.today() for row in sources if row.get("persistent")}

    def lookup(self, profile: dict, sources: List[dict], touch: bool = True) -> Dict[str, dict]:
        return {}

    def store(self, profile: dict, sources: List[dict], outcomes: Dict[str, dict],
              usage: dict, anchors: Dict[str, str]) -> None:
        return None


class TranslationCache(NullCache):
    def __init__(self, repository, team_id: str, today: Optional[str] = None):
        super().__init__(today)
        self._repository, self._team_id = repository, team_id

    def anchors(self, sources: List[dict]) -> Dict[str, str]:
        standing = [row for row in sources if row.get("persistent")]
        if not standing:
            return {}
        known = self._repository.source_anchors(
            self._team_id, [row["key"] for row in standing], self.today())
        return {row["id"]: known[row["key"]] for row in standing if row["key"] in known}

    def lookup(self, profile: dict, sources: List[dict], touch: bool = True) -> Dict[str, dict]:
        """Kept outcomes by source id. `touch` marks them used, which a
        build does and a save's check does not -- the save may be inside
        the chat approval's transaction, where it should only read."""
        standing = {row["key"]: row for row in sources if row.get("persistent")}
        if not standing:
            return {}
        rows = self._repository.compiled_sources(
            self._team_id, vocab_key(profile), compiler_id(), list(standing))
        found = {}
        for row in rows:
            source = standing.get(row["source_key"])
            outcome = to_outcome(row, source, profile) if source else None
            if outcome is not None:
                found[source["id"]] = dict(outcome, tokens=int(row.get("tokens") or 0))
        if found and touch:
            self._repository.touch_compiled_sources(
                self._team_id, [row["source_key"] for row in rows])
        return found

    def store(self, profile: dict, sources: List[dict], outcomes: Dict[str, dict],
              usage: dict, anchors: Dict[str, str]) -> None:
        kept = [row for row in sources
                if row.get("persistent") and outcomes.get(row["id"], {}).get("store")]
        if not kept:
            return
        share = int((usage or {}).get("total_tokens") or 0) // len(kept)
        self._repository.save_compiled_sources(
            self._team_id, vocab_key(profile), compiler_id(),
            [to_row(row, outcomes[row["id"]], share, anchors.get(row["id"]) or "") for row in kept])


__all__ = ["NullCache", "TranslationCache"]
