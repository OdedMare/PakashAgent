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
        from_shifts: list[str] = Query(default=[]),
        roles: list[str] = Query(default=[]),
        session: dict = Depends(manager),
    ):
        return service.replacement_options(
            session["team_id"], employee, starts_on, ends_on,
            from_shifts=from_shifts, roles=roles,
        )

    @router.post("/searches", status_code=202)
    def start_search(
        request: ReplacementSearchRequest,
        session: dict = Depends(manager),
    ):
        return service.start_replacement_search(
            session["team_id"], request.employee,
            request.starts_on, request.ends_on,
            from_shifts=request.from_shifts, roles=request.roles,
        )

    @router.get("/searches/{search_id}")
    def read_search(search_id: str, session: dict = Depends(manager)):
        return service.replacement_search(session["team_id"], search_id)

    @router.delete("/searches/{search_id}", status_code=204)
    def cancel_search(search_id: str, session: dict = Depends(manager)):
        service.cancel_replacement_search(session["team_id"], search_id)

    return router
