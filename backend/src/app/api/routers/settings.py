"""Live settings, and the model probe the settings panel uses.

The store is the single writer of `runtime-settings.json`; this router is only
the HTTP boundary onto it. Secrets never leave here in the clear — `public()`
masks them, and a patch that echoes the mask back is ignored rather than
overwriting the stored value with literal asterisks.

Boss-only. These settings are process-wide rather than per-team — they hold
the database credentials and the model API key — so with workspaces in play
they are strictly more sensitive than before, not less: a member arriving on
a share link must not read them, and one workspace's boss editing them moves
the ground under every other workspace. Guarding them as boss-only is the
floor, not the ceiling; if workspaces ever need their own model settings, the
store is what has to become per-team.

So a boss session is not enough on its own: every route here also needs the
settings password (`PAKASH_SETTINGS_PASSWORD`) in the `X-Settings-Password`
header. Anyone can open a workspace and become its boss; only the operator
knows this. Wrong guesses are throttled per workspace, and an unset password
keeps the panel locked rather than open.
"""

import hmac
from typing import Optional

from fastapi import APIRouter, Depends, Header

from app.api.contracts import ModelsProbeRequest
from app.common.errors.errors import AppError, ForbiddenError
from app.common.throttle.throttle import LoginThrottle

PASSWORD_HEADER = "X-Settings-Password"


def _settings_guard(guards, password: str, throttle: LoginThrottle):
    """The boss of some workspace who also knows the settings password."""
    boss = guards.boss()

    def check(given: Optional[str]) -> None:
        if not password:
            raise ForbiddenError("הגדרות המערכת נעולות: לא הוגדרה סיסמה בשרת")
        # Compared as bytes in constant time, so the answer's timing does not
        # say how many leading characters were right.
        if not hmac.compare_digest(
            (given or "").encode("utf-8"), password.encode("utf-8")
        ):
            raise ForbiddenError("סיסמת ההגדרות שגויה")

    def dependency(
        session: dict = Depends(boss),
        given: Optional[str] = Header(default=None, alias=PASSWORD_HEADER),
    ) -> dict:
        throttle.attempt(
            "settings:%s" % session["team_id"], lambda: check(given)
        )
        return session

    return dependency


def build_router(
    store, llm, guards, password: str = "",
    throttle: Optional[LoginThrottle] = None,
) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["settings"])
    unlocked = _settings_guard(guards, password, throttle or LoginThrottle())

    @router.get("/settings")
    def get_settings(session: dict = Depends(unlocked)) -> dict:
        """The current settings, with every secret masked."""
        return store.public()

    @router.put("/settings")
    def update_settings(patch: dict, session: dict = Depends(unlocked)) -> dict:
        """Apply a partial update and return the new masked state.

        A bad value is rejected rather than skipped, so a typo in a schema
        name or a URL is visible instead of silently doing nothing. The
        normalizers signal that with `ValueError`, which would otherwise
        escape as a 500 and a stack trace; as an `AppError` it reaches the
        panel as the 400 its message was written for.
        """
        try:
            store.update(patch)
        except (TypeError, ValueError) as exc:
            raise AppError(str(exc))
        return store.public()

    @router.get("/models")
    def models(session: dict = Depends(unlocked)) -> dict:
        """Models available on the saved connection."""
        return {"models": llm.list_models()}

    @router.post("/models")
    def probe_models(
        request: ModelsProbeRequest, session: dict = Depends(unlocked)
    ) -> dict:
        """Models available on a connection typed into the form but not yet
        saved, so a base URL or key can be tested before committing it.

        `role` selects which saved connection an omitted field falls back
        to, so each role's model list comes from the server that will
        actually serve it."""
        return {"models": llm.list_models(
            base_url_override=request.override("llm_base_url"),
            api_key_override=request.override("openai_api_key"),
            role=(request.role or "").strip(),
        )}

    return router
