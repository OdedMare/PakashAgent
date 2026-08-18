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
"""

from fastapi import APIRouter, Depends

from app.api.contracts import ModelsProbeRequest
from app.common.errors import AppError


def build_router(store, llm, guards) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["settings"])
    boss = guards.boss()

    @router.get("/settings")
    def get_settings(session: dict = Depends(boss)) -> dict:
        """The current settings, with every secret masked."""
        return store.public()

    @router.put("/settings")
    def update_settings(patch: dict, session: dict = Depends(boss)) -> dict:
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
    def models(session: dict = Depends(boss)) -> dict:
        """Models available on the saved connection."""
        return {"models": llm.list_models()}

    @router.post("/models")
    def probe_models(
        request: ModelsProbeRequest, session: dict = Depends(boss)
    ) -> dict:
        """Models available on a connection typed into the form but not yet
        saved, so a base URL or key can be tested before committing it."""
        return {"models": llm.list_models(
            base_url_override=request.override("llm_base_url"),
            api_key_override=request.override("openai_api_key"),
        )}

    return router
