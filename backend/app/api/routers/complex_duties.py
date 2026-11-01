"""`/api/complex/duty*` -- the מכלול's duties (תורנויות).

The commander's routes take the מכלול from `pakash_commander`, never from
the request; a duty type, a duty or a team of another מכלול is a 404.
`/api/complex/team-duties` is the one read a team's own commander (or the
מכלול commander inside it) has: their soldiers' duties, read only.
"""

from fastapi import APIRouter, Depends

from app.api.contracts import DutyAssignRequest, DutyTypePatch, DutyTypeRequest


class ComplexDutyRoutes:
    def __init__(self, service, guards):
        self._service = service
        self._guards = guards

    def register(self, router: APIRouter) -> None:
        self._register_types(router)
        self._register_duties(router)

        service, boss = self._service, self._guards.boss()

        @router.get("/team-duties")
        def team_duties(start: str, end: str, session: dict = Depends(boss)) -> list:
            return service.team_duties(session["team_id"], start, end)

    def _register_types(self, router: APIRouter) -> None:
        service, commander = self._service, self._guards.commander()

        @router.get("/duty-types")
        def types(session: dict = Depends(commander)) -> list:
            return service.types(session["complex_id"])

        @router.post("/duty-types")
        def create_type(
            request: DutyTypeRequest, session: dict = Depends(commander),
        ) -> dict:
            return service.create_type(session["complex_id"], request.model_dump())

        @router.patch("/duty-types/{type_id}")
        def update_type(
            type_id: str, request: DutyTypePatch,
            session: dict = Depends(commander),
        ) -> dict:
            return service.update_type(
                session["complex_id"], type_id,
                request.model_dump(exclude_unset=True),
            )

        @router.delete("/duty-types/{type_id}")
        def delete_type(type_id: str, session: dict = Depends(commander)) -> dict:
            service.delete_type(session["complex_id"], type_id)
            return {"status": "ok"}

    def _register_duties(self, router: APIRouter) -> None:
        service, commander = self._service, self._guards.commander()

        @router.get("/duties")
        def duties(start: str, end: str, session: dict = Depends(commander)) -> dict:
            return service.duties(session["complex_id"], start, end)

        @router.post("/duties")
        def assign(
            request: DutyAssignRequest, session: dict = Depends(commander),
        ) -> dict:
            """Seats one soldier for one whole day. `conflicts` lists the
            shifts it now blocks -- a warning, and still a 200."""
            return service.assign(
                session["complex_id"], request.duty_type_id, request.team_id,
                request.employee, request.duty_date, request.note,
            )

        @router.delete("/duties/{duty_id}")
        def cancel(duty_id: str, session: dict = Depends(commander)) -> dict:
            return service.cancel(session["complex_id"], duty_id)
