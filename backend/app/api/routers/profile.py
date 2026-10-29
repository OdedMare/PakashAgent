"""Boss-only manual editing of employees and shift types."""

import datetime
import logging

from fastapi import APIRouter, Depends

from app.api.contracts import ProfileUpdate, RotationPreviewRequest
from app.bl.profile_service.workplace import workplace as checked_workplace
from app.bl.rotation import weekend_preview
from app.common.errors import AgentError
from app.common.time_context import israel_today

_log = logging.getLogger("pakash.profile")


def build_router(service, guards, schedules=None) -> APIRouter:
    router = APIRouter(prefix="/api/profile", tags=["profile"])
    boss = guards.boss()

    @router.get("/compiled")
    def compiled(session: dict = Depends(boss)) -> dict:
        """How each rule, policy and note was translated for the code
        scheduler (D32). Read-only; translating happens on save."""
        return {"sources": service.compiled(session["team_id"])}

    @router.put("")
    def update(request: ProfileUpdate, session: dict = Depends(boss)) -> dict:
        """Save the profile. A new soldier or shift is then absorbed into
        every draft ahead of today (`absorbed`), moving as few rows as it
        needs; published weeks are listed, never touched."""
        team_id = session["team_id"]
        before = service.current(team_id)
        saved = service.update(team_id, **request.model_dump(exclude_unset=True))
        if schedules is None:
            return saved
        try:
            absorbed = schedules.absorb_profile_change(team_id, before, saved)
        except Exception:
            # The profile is saved either way; a refit that could not start
            # leaves the drafts as they were and the manager can rebuild.
            _log.exception("absorbing a profile change failed")
            absorbed = None
        return dict(saved, absorbed=absorbed)

    @router.post("/rotation-preview")
    def rotation_preview(request: RotationPreviewRequest, session: dict = Depends(boss)) -> dict:
        """The coming weekends of each cycle, from the setup screen's unsaved
        rows. Writes nothing; a row that would not save is named in `error`
        instead of failing the preview."""
        try:
            place = checked_workplace(request.workplace)
        except AgentError as error:
            return {"error": str(error), "cycles": {}}
        try:
            start = datetime.date.fromisoformat(request.start or "")
        except ValueError:
            start = israel_today()
        profile = {"workplace": place, "shifts": request.shifts}
        weeks = min(max(request.weeks, 1), 26)
        return {"error": "", "cycles": {
            pattern: weekend_preview(profile, pattern, start, weeks)
            for pattern in ("round", "triplet")
        }}

    @router.delete("/shifts/{name}")
    def delete_shift(name: str, session: dict = Depends(boss)) -> dict:
        """Archive a shift type: the next build stops producing it, and
        schedules already stored keep their rows."""
        return service.delete_shift(session["team_id"], name)

    return router
