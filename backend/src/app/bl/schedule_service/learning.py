"""Learning from what the manager kept correcting by hand."""

from typing import List

from app.bl.learn import observe_corrections
from app.bl.schedule_service.constants import LEARN_HISTORY
from app.bl.schedule_service.patterns import (
    pattern_evidence,
    pattern_key,
    pattern_sentence,
    worded_by_subject,
)
from app.bl.schedule_service.rows import text
from app.common.errors import AgentError
from app.dal.repository.schedules import (
    PREFERENCE_EMPLOYEE,
    PREFERENCE_GENERAL,
    PREFERENCE_SUGGESTED,
    SOURCE_AGENT,
)


class CorrectionLearning:
    def __init__(self, repository, learner):
        self._repository = repository
        self._learner = learner

    def learn_from_changes(self, team_id: str) -> dict:
        """Candidate rules from what the manager kept correcting by hand.

        Reads what the manager **decided** out of the change log, where D8
        guaranteed every override carries a stated reason. Counting first,
        and returning early when nothing repeats: the common case is
        answerable without a model call at all (D3).

        **Nothing is stored as a rule.** These are proposals the manager
        approves one at a time (D7). A model failure degrades to the counts
        alone: the panel this feeds sits beside the calendar.
        """
        corrections = self._corrections(team_id)
        if not corrections["repeated"]:
            return {
                "corrections": corrections,
                "candidate_rules": [],
                "notes": [],
                "remembered": [],
            }
        profile = self._repository.team_profile(team_id) or {}
        try:
            proposed = self._learner.propose_from_corrections(
                corrections, profile
            )
        except AgentError as error:
            proposed = {"rules": [], "notes": [str(error)]}
        return {
            "corrections": corrections,
            "candidate_rules": proposed["rules"],
            "notes": proposed["notes"],
            # What was written down as a suggestion, so the caller can say
            # "the agent noticed something" without re-reading the table.
            "remembered": self.remember(team_id, corrections, proposed["rules"]),
        }

    def observe_quietly(self, team_id: str) -> List[dict]:
        """Count the corrections and record what repeats. No model call.

        The background half of `learn_from_changes`: the manager never asks
        for this and never waits on it. The *pattern* is arithmetic (D3) and
        arithmetic is what may run unattended; everything it writes is a
        `suggested`, inert, visible row (D21). Never raises.
        """
        try:
            return self.remember(team_id, self._corrections(team_id), [])
        except Exception:
            return []

    def remember(
        self, team_id: str, corrections: dict, rules: List[dict]
    ) -> List[dict]:
        """Write repeated corrections down as suggestions, once each.

        **Deduplicated on the pattern, not on the wording**, and across every
        state: the same pattern observed again is the same observation, and a
        dismissed suggestion that came back would be a decision overruled by
        a cron.
        """
        repeated = (corrections or {}).get("repeated") or []
        if not repeated:
            return []
        seen = {
            text(row.get("subject"))
            for row in self._repository.preferences(team_id)
            if text(row.get("source")) == SOURCE_AGENT
        }
        # The model's wording where there is one, the counted sentence
        # otherwise. Either way the sentence is a proposal, not a rule.
        worded = worded_by_subject(rules, repeated)
        remembered = []
        for entry in repeated:
            subject = pattern_key(entry)
            if not subject or subject in seen:
                continue
            seen.add(subject)
            remembered.append(self._suggest(team_id, entry, subject, worded))
        return remembered

    def _suggest(
        self, team_id: str, entry: dict, subject: str, worded: dict
    ) -> dict:
        return self._repository.create_preference(
            team_id,
            text=worded.get(subject) or pattern_sentence(entry),
            kind=PREFERENCE_EMPLOYEE if entry.get("employee")
            else PREFERENCE_GENERAL,
            subject=subject,
            evidence=pattern_evidence(entry),
            status=PREFERENCE_SUGGESTED,
            source=SOURCE_AGENT,
        )

    def _corrections(self, team_id: str) -> dict:
        return observe_corrections(
            self._repository.change_log(team_id, limit=LEARN_HISTORY)
        )
