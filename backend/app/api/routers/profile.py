"""Boss-only manual editing of employees and shift types."""

import logging

from fastapi import APIRouter, Depends

from app.api.contracts import ProfileUpdate

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

    @router.delete("/shifts/{name}")
    def delete_shift(name: str, session: dict = Depends(boss)) -> dict:
        """Archive a shift type: the next build stops producing it, and
        schedules already stored keep their rows."""
        return service.delete_shift(session["team_id"], name)

    return router
