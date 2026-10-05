"""Liveness, plus a database round-trip."""

from fastapi import APIRouter


def build_router(repository) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["health"])

    @router.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @router.get("/health/database")
    def database_health() -> dict:
        return repository.health()

    return router
