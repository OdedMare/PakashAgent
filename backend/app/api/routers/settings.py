"""Live settings, and the model probe the settings panel uses.

The store is the single writer of `runtime-settings.json`; this router is only
the HTTP boundary onto it. Secrets never leave here in the clear — `public()`
masks them, and a patch that echoes the mask back is ignored rather than
overwriting the stored value with literal asterisks.

PakashAgent is single-tenant and local, so these routes carry no auth guard.
If that ever changes, the guard belongs here, not in the store.
"""

from fastapi import APIRouter

from app.api.contracts import ModelsProbeRequest


def build_router(store, llm) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["settings"])

    @router.get("/settings")
    def get_settings() -> dict:
        """The current settings, with every secret masked."""
        return store.public()

    @router.put("/settings")
    def update_settings(patch: dict) -> dict:
        """Apply a partial update and return the new masked state.

        A bad value raises rather than being skipped — the panel shows the
        message, so a typo in a schema name or URL is visible instead of
        silently doing nothing.
        """
        store.update(patch)
        return store.public()

    @router.get("/models")
    def models() -> dict:
        """Models available on the saved connection."""
        return {"models": llm.list_models()}

    @router.post("/models")
    def probe_models(request: ModelsProbeRequest) -> dict:
        """Models available on a connection typed into the form but not yet
        saved, so a base URL or key can be tested before committing it."""
        return {"models": llm.list_models(
            base_url_override=request.override("llm_base_url"),
            api_key_override=request.override("openai_api_key"),
        )}

    return router
