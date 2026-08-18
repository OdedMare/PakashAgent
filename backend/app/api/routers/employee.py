"""The employee's own area: claim an identity, read your hours, ask for a day.

The HTTP half of [D14](../../../docs/DECISIONS.md#d14--employees-get-real-identities-and-may-submit-constraints-️-reverses-d5-amends-d10).

**Every route here is scoped by a name taken off the signed cookie**, never
from the body or the path. That is the entire access control of this surface:
a signed-in employee cannot read a colleague's hours, their stated reasons, or
their pending requests, because there is nowhere to put another name.

**Nothing here mutates a schedule.** The one write an employee gets is a
constraint *request*, which lands as pending and is invisible to `bl/audit.py`
until a manager approves it. Routes that decide requests depend on
`guards.boss()` -- the manager remains the sole decider, exactly as before.

Route order matters, as it does in `schedules.py`: literal paths are declared
before `/{request_id}`, or a path parameter swallows them.
"""

from fastapi import APIRouter, Depends, Response

from app.api.contracts import (
    ClaimRequest,
    ConstraintSubmission,
    EmployeeLoginRequest,
    ReleaseRequest,
    RequestDecision,
)
from app.common.sessions import COOKIE_NAME, ROLE_EMPLOYEE, issue


def build_router(service, guards, secret: str, days: int) -> APIRouter:
    router = APIRouter(prefix="/api/employee", tags=["employee"])
    boss = guards.boss()
    visitor = guards.visitor()
    employee = guards.employee()

    def _sign_in(response: Response, team_id: str, name: str) -> None:
        """Upgrade the current session to a personal one.

        Same cookie and same flags as the workspace login -- see
        `routers/workspace.py` for why `secure` is left to the reverse proxy.
        The name is signed into the payload, which is what every read below
        filters on.
        """
        response.set_cookie(
            COOKIE_NAME,
            issue(secret, team_id, ROLE_EMPLOYEE, days, employee=name),
            max_age=days * 86400,
            httponly=True,
            samesite="lax",
            path="/",
        )

    # -- identity ----------------------------------------------------------

    @router.get("/roster")
    def roster(session: dict = Depends(visitor)) -> dict:
        """Names available to claim, and which are taken.

        Reachable with a plain share-link session -- it is the screen someone
        sees *before* they have an identity. Carries names and a claimed flag
        only, never a last-seen time: who signed in when is the manager's
        view, not a stranger-with-the-link's.
        """
        return service.roster(session["team_id"])

    @router.post("/claim")
    def claim(
        request: ClaimRequest,
        response: Response,
        session: dict = Depends(visitor),
    ) -> dict:
        """Claim a roster name, then sign in as it immediately.

        Signing in here rather than bouncing to the login form is deliberate:
        the passcode was just chosen and typing it again proves nothing.
        """
        result = service.claim(
            session["team_id"], request.employee, request.passcode
        )
        _sign_in(response, session["team_id"], result["employee"])
        return result

    @router.post("/login")
    def login(
        request: EmployeeLoginRequest,
        response: Response,
        session: dict = Depends(visitor),
    ) -> dict:
        result = service.login(
            session["team_id"], request.employee, request.passcode
        )
        _sign_in(response, session["team_id"], result["employee"])
        return result

    @router.post("/logout")
    def logout(response: Response) -> dict:
        """Sign out of the personal identity.

        Clears the cookie entirely rather than downgrading to a member
        session: the share link is what grants that, and re-following it is
        how someone gets back to the read-only view.
        """
        response.delete_cookie(COOKIE_NAME, path="/")
        return {"status": "ok"}

    # -- the personal view -------------------------------------------------

    @router.get("/me")
    def me(session: dict = Depends(employee)) -> dict:
        """Hours, shifts, warnings, teammates, history and requests.

        One call because the personal area renders them together, and a
        half-loaded screen is worse than a slightly slower one -- the same
        reasoning as the management overview.
        """
        return service.me(session["team_id"], session["employee"])

    @router.post("/acknowledge")
    def acknowledge(session: dict = Depends(employee)) -> dict:
        """Mark the changes just shown as read (D16).

        Sent by the personal area once it has rendered them, never by the
        login: the point is that a person *saw* the moves affecting them, and
        arriving is not seeing.

        The employee comes from the signed cookie, so this can only ever
        settle the caller's own badge.
        """
        return service.acknowledge(session["team_id"], session["employee"])

    # -- constraint requests, employee side --------------------------------

    @router.get("/requests")
    def my_requests(session: dict = Depends(employee)) -> list:
        return service.my_requests(session["team_id"], session["employee"])

    @router.post("/requests")
    def submit(
        request: ConstraintSubmission, session: dict = Depends(employee)
    ) -> dict:
        """Submit a constraint request.

        `200` with a pending row. Nothing about the schedule changed, and the
        response says so by carrying `status: "pending"` rather than a
        constraint.
        """
        return service.submit(
            session["team_id"],
            session["employee"],
            request.constraint_date,
            shift_name=request.shift_name,
            available=request.available,
            reason=request.reason,
        )

    @router.post("/requests/{request_id}/withdraw")
    def withdraw(
        request_id: str, session: dict = Depends(employee)
    ) -> dict:
        """Take back a pending request. Scoped to the caller's own rows."""
        return service.withdraw(
            session["team_id"], session["employee"], request_id
        )

    return router


def build_manager_router(service, guards) -> APIRouter:
    """The manager's side of the same feature.

    A separate router under `/api/schedule/requests` rather than more routes
    on the one above, so that the guard is unmistakable at a glance: every
    route in this function depends on `boss`, and none of them could be
    reached by an employee cookie even if a prefix were mistyped.
    """
    router = APIRouter(prefix="/api/schedule/requests", tags=["requests"])
    boss = guards.boss()

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
    def release(
        request: ReleaseRequest, session: dict = Depends(boss)
    ) -> dict:
        service.release(session["team_id"], request.employee)
        return {"status": "ok"}

    @router.post("/{request_id}/approve")
    def approve(
        request_id: str,
        request: RequestDecision,
        session: dict = Depends(boss),
    ) -> dict:
        """Approve, and write the constraint it becomes.

        This is the moment the request starts counting: the `availability`
        row it creates is what `bl/audit.py` reads, so the warning about
        scheduling someone on a day they cannot work appears now — not while
        the request was pending.
        """
        return service.approve(
            session["team_id"], request_id, request.reason
        )

    @router.post("/{request_id}/reject")
    def reject(
        request_id: str,
        request: RequestDecision,
        session: dict = Depends(boss),
    ) -> dict:
        """Reject, with a reason the employee will read."""
        return service.reject(session["team_id"], request_id, request.reason)

    return router
