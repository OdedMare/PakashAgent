"""A period leaving as a file (D17), and old files coming in (D7)."""

from typing import List

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import Response

from app.api.contracts import ImportConfirmRequest, ImportPreview, Schedule
from app.api.routers.schedules.base import RouteGroup

_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class TransferRoutes(RouteGroup):
    def register(self, router: APIRouter) -> None:
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

        @router.post("/import/preview", response_model=ImportPreview)
        async def import_preview(
            files: List[UploadFile] = File(...),
            learn_rules: bool = True,
            session: dict = Depends(boss),
        ) -> dict:
            """Read uploaded schedule files and return an interpretation.

            **This route writes nothing** (D7): `/import/confirm` is the only
            endpoint that persists, which is what makes the confirmation real.
            Takes many files at once because patterns worth learning are only
            visible across them.
            """
            uploads = [
                {"filename": upload.filename or "", "content": await upload.read()}
                for upload in files or []
            ]
            return service.preview_import(
                session["team_id"], uploads, learn_rules=learn_rules
            )

        @router.post("/import/confirm", response_model=Schedule)
        def import_confirm(
            request: ImportConfirmRequest, session: dict = Depends(boss)
        ) -> dict:
            """Store an interpretation the manager approved (D7).

            The rows come from the request rather than a re-read of the file,
            so what is stored is exactly what was shown and approved.
            """
            return service.commit_import(
                session["team_id"],
                [row.model_dump() for row in request.assignments],
                [row.model_dump() for row in request.unavailability],
                starts_on=request.starts_on,
                ends_on=request.ends_on,
            )
