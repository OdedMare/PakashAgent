"""The replacement tab: who could cover an absence. Reads only.

The tab asks here, the manager picks, and the picks go to the conversation
as an ordinary message -- so a replacement still becomes a plan through the
one write path and the one approval (D12/D19), never through this route.
"""

from fastapi import APIRouter, Depends, Query


def build_router(service, guards):
    router = APIRouter(prefix="/api/agent/replacements", tags=["manager chat"])
    manager = guards.manager()

    @router.get("")
    def replacements(
        employee: str = Query(min_length=1, max_length=120),
        starts_on: str = Query(min_length=10, max_length=10),
        ends_on: str = Query(default="", max_length=10),
        session: dict = Depends(manager),
    ):
        return service.replacement_options(
            session["team_id"], employee, starts_on, ends_on,
        )

    return router
