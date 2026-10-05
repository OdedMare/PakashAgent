"""Constraints, the change log, and the preferences the agent remembers."""

from typing import List, Optional

from fastapi import APIRouter, Depends

from app.api.contracts import (
    ConstraintRequest, Preference, PreferenceRequest, PreferenceUpdate,
)
from app.api.routers.schedules.base import RouteGroup

_OK = {"status": "ok"}


class ConstraintRoutes(RouteGroup):
    def register(self, router: APIRouter) -> None:
        service, boss, visitor = self.service, self.boss, self.visitor

        @router.get("/constraints/list")
        def constraints(
            starts_on: Optional[str] = None,
            ends_on: Optional[str] = None,
            employee: Optional[str] = None,
            session: dict = Depends(visitor),
        ):
            """Recorded constraints. Readable by the team, writable by the manager."""
            return service.constraints(session["team_id"], starts_on, ends_on, employee)

        @router.post("/constraints")
        def set_constraint(request: ConstraintRequest, session: dict = Depends(boss)):
            """Record a constraint. Boss-only: employees never write (D5)."""
            return service.set_constraint(
                session["team_id"],
                request.employee,
                request.constraint_date,
                shift_name=request.shift_name,
                available=request.available,
                start_time=request.start_time,
                end_time=request.end_time,
                is_hard=request.is_hard,
                reason=request.reason,
                source=request.source,
            )

        @router.delete("/constraints/{row_id}")
        def delete_constraint(row_id: str, session: dict = Depends(boss)) -> dict:
            service.delete_constraint(row_id, session["team_id"])
            return _OK

        @router.get("/history/list")
        def history(
            schedule_id: Optional[str] = None, session: dict = Depends(visitor),
        ):
            """The append-only change log — the only history there is (D4)."""
            return service.history(session["team_id"], schedule_id)

        @router.get("/history/learn")
        def learn_from_changes(session: dict = Depends(boss)) -> dict:
            """Candidate rules from what the manager kept correcting by hand.

            Boss-only and read-only: these are proposals the manager approves
            one at a time (D7), exactly like the candidates an import produces.
            """
            return service.learn_from_changes(session["team_id"])


class PreferenceRoutes(RouteGroup):
    """Boss-only and visible by design: a stored preference the manager
    cannot see is a rule they never agreed to (D21)."""

    def register(self, router: APIRouter) -> None:
        service, boss = self.service, self.boss

        @router.get("/preferences/list", response_model=List[Preference])
        def preferences(status: Optional[str] = None, session: dict = Depends(boss)):
            """What this workplace has taught the agent."""
            return service.preferences(session["team_id"], status=status)

        @router.post("/preferences", response_model=Preference)
        def add_preference(
            request: PreferenceRequest, session: dict = Depends(boss)
        ) -> dict:
            """Record a preference, or propose one for approval.

            `suggested: true` stores it inert -- `ask()` reads only active
            ones, so a proposal changes nothing until the manager approves it.
            """
            return service.add_preference(
                session["team_id"],
                text=request.text,
                kind=request.kind,
                subject=request.subject,
                evidence=request.evidence,
                suggested=request.suggested,
            )

        @router.patch("/preferences/{row_id}", response_model=Preference)
        def update_preference(
            row_id: str, request: PreferenceUpdate, session: dict = Depends(boss),
        ) -> dict:
            """Reword a preference, approve a suggested one, or archive it."""
            return service.update_preference(
                session["team_id"], row_id, text=request.text, status=request.status,
            )

        @router.delete("/preferences/{row_id}")
        def delete_preference(row_id: str, session: dict = Depends(boss)) -> dict:
            service.delete_preference(session["team_id"], row_id)
            return _OK
