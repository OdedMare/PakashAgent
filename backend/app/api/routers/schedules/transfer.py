"""A period leaving as a file (D17), and the workplace's own files coming in (D7/D42)."""

import json

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import Response
from pydantic import ValidationError

from app.api.contracts import ImportConfirmRequest, ImportOptions, ImportPreview, Schedule
from app.api.routers.schedules.base import RouteGroup
from app.common.errors import AppError

_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class TransferRoutes(RouteGroup):
    def register(self, router: APIRouter) -> None:
        self._register_export(router)
        self._register_import(router)

    def _register_export(self, router: APIRouter) -> None:
        """A period leaving as a file (D17)."""
        service, boss = self.service, self.boss

        @router.get("/export/{schedule_id}")
        def export(schedule_id: str, session: dict = Depends(boss)) -> Response:
            """One period as an `.xlsx` download.

            Boss-only: a file is a copy that leaves the app entirely. The
            filename is ASCII on purpose -- a Hebrew one travels badly through
            `Content-Disposition`.
            """
            content, name = service.workbook(session["team_id"], schedule_id)
            return Response(
                content=content,
                media_type=_XLSX,
                headers={"Content-Disposition": 'attachment; filename="%s"' % name},
            )

    def _register_import(self, router: APIRouter) -> None:
        """A file coming in: preview, then confirm (D7/D42)."""
        service, boss = self.service, self.boss

        @router.post("/import/preview", response_model=ImportPreview)
        async def import_preview(
            file: UploadFile = File(...),
            options: str = Form(default="{}"),
            session: dict = Depends(boss),
        ) -> dict:
            """Read one uploaded file and say what it holds.

            **This route writes nothing** (D7): `/import/confirm` is the only
            one that persists. The screen sends the same file again with
            `options` -- the manager's corrections to the layout, the names
            and the shifts -- and gets the file re-read with them.
            """
            content = await file.read()
            choices = _options(options)
            return service.preview_import(
                session["team_id"], content, filename=file.filename or "",
                sheet=choices.sheet,
                layout=choices.layout.model_dump() if choices.layout else None,
                week_start=choices.week_start, hint=choices.hint,
                names=choices.names, shifts=choices.shifts, use_model=choices.use_model,
                date_from=choices.date_from, date_to=choices.date_to, year=choices.year,
            )

        @router.post("/import/confirm", response_model=Schedule)
        def import_confirm(request: ImportConfirmRequest, session: dict = Depends(boss)) -> dict:
            """Store what the manager approved. The rows come from the request,
            not a re-read of the file, so what is stored is what was shown."""
            return service.commit_import(
                session["team_id"],
                [row.model_dump() for row in request.assignments],
                [row.model_dump() for row in request.unavailability],
                schedule_id=request.schedule_id, filename=request.filename,
            )


def _options(raw: str) -> ImportOptions:
    """The form field's JSON, refused in Hebrew rather than as a 422 nobody reads."""
    try:
        return ImportOptions.model_validate(json.loads(raw or "{}"))
    except (ValueError, ValidationError):
        raise AppError("אפשרויות הייבוא אינן תקינות")
