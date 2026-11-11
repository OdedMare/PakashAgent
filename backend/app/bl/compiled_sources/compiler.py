"""`SourceCompiler`: translate what setup wrote before any build asks for it.

Saving the setup form stays what it always was -- synchronous, validated in
code, no model call. What it does in addition is `queue`: if any standing
source has no kept translation for today's roster and compiler, one
`compile_sources` job goes onto the durable queue (`copilot_jobs`), and the
worker's `compile` translates them in the background. Saving twice before
the worker runs queues one job: the key names the sources that are missing.

Nothing here is required for a build to be right. A job that never runs,
fails, or finds no model leaves those sources to be translated by the next
build, as they always were.
"""

import datetime
import hashlib
import logging
from typing import List, Optional

from app.bl.compiled_sources.cache import TranslationCache
from app.bl.compiled_sources.keys import compiler_id, vocab_key
from app.bl.scheduler.directives import semantic_sources
from app.dal.repository.schedules import PREFERENCE_ACTIVE

JOB_KIND = "compile_sources"
# Sources per model call: the bounds of `DirectiveAgent` were set for one
# build's worth of sources, not for a whole setup at once.
BATCH_SIZE = 12

_log = logging.getLogger("pakash.compiled_sources")


def standing_sources(repository, team_id: str, profile: Optional[dict] = None) -> List[dict]:
    """Every standing source the team has: the profile's and its active preferences'."""
    profile = profile if profile is not None else repository.team_profile(team_id) or {}
    preferences = (repository.preferences(team_id, status=PREFERENCE_ACTIVE)
                   if hasattr(repository, "preferences") else [])
    return [row for row in semantic_sources(profile, preferences=preferences)
            if row.get("persistent")]


def queue(repository, team_id: str, profile: Optional[dict] = None) -> bool:
    """Queue translating whatever standing source is not kept yet. Never
    raises: a save that succeeded must not report failure over this."""
    if not hasattr(repository, "compiled_sources") or not hasattr(repository, "enqueue_copilot_job"):
        return False
    try:
        profile = profile if profile is not None else repository.team_profile(team_id) or {}
        sources = standing_sources(repository, team_id, profile)
        found = TranslationCache(repository, team_id).lookup(profile, sources, touch=False)
        missing = sorted(row["key"] for row in sources if row["id"] not in found)
        if not missing:
            return False
        digest = hashlib.sha256("|".join(
            [vocab_key(profile), compiler_id()] + missing).encode("utf-8")).hexdigest()[:32]
        return bool(repository.enqueue_copilot_job(team_id, "compile:" + digest, kind=JOB_KIND))
    except Exception:  # noqa: BLE001 - the save already happened
        _log.exception("could not queue translating standing sources team=%s", team_id)
        return False


class SourceCompiler:
    def __init__(self, repository, llm, today: Optional[str] = None):
        self._repository, self._llm, self._today = repository, llm, today

    def compile(self, team_id: str) -> int:
        """Translate and keep every missing standing source; how many were kept.

        Reads the profile as it is now, not as it was when the job was
        queued, so a later save is never undone by an earlier job."""
        from app.bl.directive_agent import DirectiveAgent

        profile = self._repository.team_profile(team_id) or {}
        cache = TranslationCache(self._repository, team_id, today=self._today)
        sources = standing_sources(self._repository, team_id, profile)
        found = cache.lookup(profile, sources)
        missing = [row for row in sources if row["id"] not in found]
        starts_on, ends_on = _reference_week(cache.today())
        agent, kept = DirectiveAgent(self._llm), 0
        for start in range(0, len(missing), BATCH_SIZE):
            outcomes = agent.compile(profile, missing[start:start + BATCH_SIZE],
                                     starts_on, ends_on, cache)
            if outcomes is None:
                break  # No model, or none reachable: the next build translates.
            kept += sum(1 for row in outcomes.values() if row.get("store"))
        self._repository.prune_compiled_sources(team_id)
        return kept


def _reference_week(today: str):
    """The coming Sunday-to-Saturday week: what the tools look at while compiling."""
    day = datetime.date.fromisoformat(today)
    sunday = day + datetime.timedelta(days=(6 - day.weekday()) % 7 or 7)
    return sunday.isoformat(), (sunday + datetime.timedelta(days=6)).isoformat()


__all__ = ["BATCH_SIZE", "JOB_KIND", "SourceCompiler", "queue", "standing_sources"]
