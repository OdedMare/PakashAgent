"""The period leaving as a file (D17)."""

from typing import Optional

from app.bl.export import as_workbook, filename
from app.bl.schedule_service import rows
from app.bl.schedule_service.context import ScheduleContext


class WorkbookExporter:
    """One period as `.xlsx`, in Sample A's layout (D17).

    The unaudited stored schedule is passed deliberately: an export is a
    picture of what was decided, and warnings are advice about it, not part
    of the roster people read.
    """

    def __init__(self, context: ScheduleContext):
        self._context = context

    def workbook(
        self, team_id: str, schedule_id: Optional[str] = None
    ) -> tuple:
        schedule = self._context.require_schedule(team_id, schedule_id)
        title = rows.workplace_name(self._context.profile(team_id))
        return as_workbook(schedule, title=title), filename(schedule, "xlsx")
