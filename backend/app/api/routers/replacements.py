"""The replacement tab: who could cover an absence. Reads only.

The tab asks here, the manager picks, and the picks go to the conversation
as an ordinary message -- so a replacement still becomes a plan through the
one write path and the one approval (D12/D19), never through this route.
"""

from fastapi import APIRouter, Depends, Query

from app.api.contracts import ReplacementSearchRequest


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

    @router.post("/searches", status_code=202)
    def start_search(
        request: ReplacementSearchRequest,
        session: dict = Depends(manager),
    ):
        return service.start_replacement_search(
            session["team_id"], request.employee,
            request.starts_on, request.ends_on,
        )

    @router.get("/searches/{search_id}")
    def read_search(search_id: str, session: dict = Depends(manager)):
        return service.replacement_search(session["team_id"], search_id)

    return router
