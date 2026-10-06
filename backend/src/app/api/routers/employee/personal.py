"""The signed-in employee's own view, constraint requests, and swap offers.

Every route takes the employee from `session["employee"]` on the signed
cookie, never from the body or the path (D14).
"""

from fastapi import APIRouter, Depends

from app.api.contracts import (
    AssistantQuestion, ConstraintSubmission, SwapAnswer, SwapProposal,
)


class PersonalRoutes:
    def __init__(self, service, employee):
        self._service = service
        self._employee = employee

    def register(self, router: APIRouter) -> None:
        service, employee = self._service, self._employee

        @router.get("/me")
        def me(session: dict = Depends(employee)) -> dict:
            """Hours, shifts, warnings, teammates, history and requests.

            One call because the personal area renders them together.
            """
            return service.me(session["team_id"], session["employee"])

        @router.post("/assistant")
        def assistant(request: AssistantQuestion, session: dict = Depends(employee)) -> dict:
            """Ask about swaps or one's own week (D27). Writes nothing.

            `suggestions` are swaps already checked clean; offering one is
            the ordinary `POST /swaps`, sent by the employee's own click.
            """
            return service.ask(
                session["team_id"],
                session["employee"],
                request.question,
                history=[turn.model_dump() for turn in request.history],
            )

        @router.post("/acknowledge")
        def acknowledge(session: dict = Depends(employee)) -> dict:
            """Mark the changes just shown as read (D16).

            Sent by the personal area once it has rendered them, never by the
            login: arriving is not seeing.
            """
            return service.acknowledge(session["team_id"], session["employee"])

        @router.get("/requests")
        def my_requests(session: dict = Depends(employee)) -> list:
            return service.my_requests(session["team_id"], session["employee"])

        @router.post("/requests")
        def submit(request: ConstraintSubmission, session: dict = Depends(employee)) -> dict:
            """Submit a constraint request. `200` with a *pending* row."""
            return service.submit(
                session["team_id"],
                session["employee"],
                request.constraint_date,
                shift_name=request.shift_name,
                available=request.available,
                reason=request.reason,
            )

        @router.post("/requests/{request_id}/withdraw")
        def withdraw(request_id: str, session: dict = Depends(employee)) -> dict:
            """Take back a pending request. Scoped to the caller's own rows."""
            return service.withdraw(session["team_id"], session["employee"], request_id)


class EmployeeSwapRoutes:
    """Swap offers between colleagues. **None of these moves anything.**"""

    def __init__(self, service, employee):
        self._service = service
        self._employee = employee

    def register(self, router: APIRouter) -> None:
        service, employee = self._service, self._employee

        @router.get("/swaps")
        def my_swaps(session: dict = Depends(employee)) -> list:
            """Swaps naming the caller, on either side, labelled by side."""
            return service.my_swaps(session["team_id"], session["employee"])

        @router.get("/swaps/incoming")
        def incoming_swaps(session: dict = Depends(employee)) -> list:
            """Offers waiting on the caller's answer. Declared before
            `/{swap_id}/...` so the path parameter cannot swallow it."""
            return service.incoming_swaps(session["team_id"], session["employee"])

        @router.post("/swaps")
        def propose_swap(request: SwapProposal, session: dict = Depends(employee)) -> dict:
            """Offer a colleague a trade: `awaiting_counterparty`, nothing moved."""
            return service.propose_swap(
                session["team_id"],
                session["employee"],
                request.assignment_id,
                request.counterparty,
                request.counterparty_assignment_id,
                reason=request.reason,
            )

        @router.post("/swaps/{swap_id}/answer")
        def answer_swap(
            swap_id: str, request: SwapAnswer, session: dict = Depends(employee),
        ) -> dict:
            """Accept or decline an offer.

            Scoped to the counterparty inside the repository. Accepting still
            moves nothing: it puts the swap in the manager's inbox.
            """
            return service.answer_swap(
                session["team_id"], session["employee"], swap_id, request.agreed
            )

        @router.post("/swaps/{swap_id}/withdraw")
        def withdraw_swap(swap_id: str, session: dict = Depends(employee)) -> dict:
            """The requester taking back their own offer."""
            return service.withdraw_swap(session["team_id"], session["employee"], swap_id)
