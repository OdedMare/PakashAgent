"""The manager's side: ruling on constraint requests and on swaps.

Separate routers on their own prefixes so the guard is unmistakable at a
glance: every route here depends on `boss`, and none could be reached by an
employee cookie even if a prefix were mistyped. It also keeps `/{request_id}`
and `/{swap_id}` in different routers, where they cannot shadow one another.
"""

from fastapi import APIRouter, Depends

from app.api.contracts import ReleaseRequest, RequestDecision


class RequestDecisionRoutes:
    def __init__(self, service, boss):
        self._service = service
        self._boss = boss

    def register(self, router: APIRouter) -> None:
        service, boss = self._service, self._boss

        @router.get("")
        def all_requests(session: dict = Depends(boss)) -> list:
            return service.all_requests(session["team_id"])

        @router.get("/pending")
        def pending(session: dict = Depends(boss)) -> list:
            """The inbox. Declared before `/{request_id}` on purpose."""
            return service.pending(session["team_id"])

        @router.get("/identities")
        def identities(session: dict = Depends(boss)) -> list:
            """Who has claimed a name, and when they were last seen."""
            return service.identities(session["team_id"])

        @router.post("/identities/release")
        def release(request: ReleaseRequest, session: dict = Depends(boss)) -> dict:
            service.release(session["team_id"], request.employee)
            return {"status": "ok"}

        @router.post("/{request_id}/approve")
        def approve(
            request_id: str, request: RequestDecision, session: dict = Depends(boss),
        ) -> dict:
            """Approve, and write the constraint it becomes.

            The `availability` row it creates is what `bl/audit.py` reads, so
            the request starts counting now -- not while it was pending.
            """
            return service.approve(session["team_id"], request_id, request.reason)

        @router.post("/{request_id}/reject")
        def reject(
            request_id: str, request: RequestDecision, session: dict = Depends(boss),
        ) -> dict:
            """Reject, with a reason the employee will read."""
            return service.reject(session["team_id"], request_id, request.reason)


class SwapDecisionRoutes:
    def __init__(self, service, boss):
        self._service = service
        self._boss = boss

    def register(self, router: APIRouter) -> None:
        service, boss = self._service, self._boss

        @router.get("")
        def all_swaps(session: dict = Depends(boss)) -> list:
            return service.all_swaps(session["team_id"])

        @router.get("/pending")
        def pending(session: dict = Depends(boss)) -> list:
            """The inbox: swaps both employees have agreed to.

            One still awaiting its counterparty is deliberately absent -- an
            offer nobody has accepted is not yet an arrangement.
            """
            return service.pending_swaps(session["team_id"])

        @router.post("/{swap_id}/approve")
        def approve(
            swap_id: str, request: RequestDecision, session: dict = Depends(boss),
        ) -> dict:
            """Approve, and perform the swap.

            The only route in the feature that moves an assignment, through
            the same `OP_SWAP` path a manager-typed swap takes. The reason is
            required: this *changes a schedule*, and D8 does not exempt a
            change for having been suggested by the people it affects.
            """
            return service.approve_swap(session["team_id"], swap_id, request.reason)

        @router.post("/{swap_id}/reject")
        def reject(
            swap_id: str, request: RequestDecision, session: dict = Depends(boss),
        ) -> dict:
            """Refuse a swap, with a reason both employees will read."""
            return service.reject_swap(session["team_id"], swap_id, request.reason)
