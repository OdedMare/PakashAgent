"""Whether a profile can carry a grid, and what to say when it cannot."""

from app.bl.schedule_service.rows import has_shifts
from app.common.errors import AgentError, ProfileIncompleteError


class ProfileGate:
    """The one answer to "is this profile enough to build a period from".

    Every building path asks this, so there is one answer to it. `generate`
    and `create_blank` differ in whether a model runs; they do not differ in
    what a profile has to contain before a grid exists, and when they each
    checked separately the manual path grew a second, vaguer definition of
    "not enough".

    Two distinct failures, deliberately not merged:

    - **No profile at all.** The interview was never run. There is nothing
      to resume, so this stays a plain `AgentError`.
    - **A profile that cannot carry a grid.** The interview ended early
      through `interview_service.end` and recorded what it still owes on
      `completeness`. That record is read back through `profile_gaps` rather
      than recomputed, so the gate and the agent's own answer to *"what are
      you missing"* can never drift apart. It is a `ProfileIncompleteError`
      because the manager can fix it -- the missing topics travel with it.

    Shift vocabulary is the only true stop. Missing rules or employees
    degrade the result, and refusing over them would be worse than building
    a thin week: D9 forbids inventing shift names, but nothing forbids
    scheduling a roster the agent knows little about.
    """

    def __init__(self, repository, tools):
        self._repository = repository
        self._tools = tools

    def buildable_profile(self, team_id: str) -> dict:
        profile = self._repository.team_profile(team_id)
        if not profile:
            raise AgentError(
                "צריך להשלים את ראיון ההיכרות לפני בניית סידור"
            )
        if has_shifts(profile):
            return profile
        # Asked only once the answer is known to be a refusal: `profile_gaps`
        # is read here to *explain* this failure rather than to detect it.
        gaps = self._tools.profile_gaps(team_id)
        raise ProfileIncompleteError(
            "לא ניתן לבנות סידור: לא הוגדרו סוגי משמרות בראיון ההיכרות. "
            "אפשר להשלים את החסר בשיחה עם הסוכן.",
            gaps=gaps.get("gaps") or [],
            blocks=gaps.get("blocks") or [],
        )
