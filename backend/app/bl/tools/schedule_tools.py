"""`ScheduleTools`: the read-only operations the agent runs on one workspace."""

import datetime
import inspect
from typing import Callable, Dict, Optional

from app.bl.tools.coverage_tools import CoverageGaps, PublishReadiness
from app.bl.tools.names import (
    TOOL_COVERAGE_GAPS, TOOL_EMPLOYEE_STATE, TOOL_FIND_REPLACEMENTS,
    TOOL_PROFILE_GAPS, TOOL_PUBLISH_READINESS, TOOL_READ_PERIOD,
    TOOL_TEAM_OVERVIEW, TOOL_VALIDATE_PLACEMENT,
)
from app.bl.tools.period_tools import EmployeeState, ReadPeriod, TeamOverview
from app.bl.tools.placement_tools import FindReplacements, ValidatePlacement
from app.bl.tools.profile_tools import ProfileGaps
from app.bl.tools.reads import ToolReads
from app.bl.tools.values import text
from app.common.errors import AgentError

_DATE_ARGUMENTS = ("day", "slot_date", "starts_on", "ends_on")


class ScheduleTools:
    """Each tool is an attribute, callable as `tools.read_period(team_id)`.

    Holds no state beyond the repository handle: two managers asking the same
    question at the same moment share nothing.
    """

    def __init__(self, repository):
        reads = ToolReads(repository)
        self.team_overview = TeamOverview(reads)
        self.read_period = ReadPeriod(reads)
        self.employee_state = EmployeeState(reads)
        self.coverage_gaps = CoverageGaps(reads)
        self.validate_placement = ValidatePlacement(reads)
        self.find_replacements = FindReplacements(reads)
        self.publish_readiness = PublishReadiness(reads, self.coverage_gaps)
        self.profile_gaps = ProfileGaps(reads)
        self._menu: Dict[str, Callable] = {
            TOOL_READ_PERIOD: self.read_period,
            TOOL_TEAM_OVERVIEW: self.team_overview,
            TOOL_EMPLOYEE_STATE: self.employee_state,
            TOOL_COVERAGE_GAPS: self.coverage_gaps,
            TOOL_VALIDATE_PLACEMENT: self.validate_placement,
            TOOL_FIND_REPLACEMENTS: self.find_replacements,
            TOOL_PUBLISH_READINESS: self.publish_readiness,
            TOOL_PROFILE_GAPS: self.profile_gaps,
        }

    def run(self, team_id: str, name: str, arguments: Optional[dict] = None) -> dict:
        """Dispatch one named tool call. The planner's only entry point.

        Returns `{"tool", "ok", ...}` whatever happens, including for a name
        that does not exist: the planning loop feeds this straight back to the
        model, so a failure has to be describable rather than thrown.
        """
        name = text(name)
        arguments = arguments if isinstance(arguments, dict) else {}
        invalid = _invalid_date_argument(arguments)
        if invalid:
            return _failure(
                name, "%s חייב להיות תאריך מוחלט בפורמט YYYY-MM-DD" % invalid
            )
        tool = self._menu.get(name)
        if tool is None:
            return _failure(name, "אין כלי בשם הזה")
        try:
            result = tool(team_id, **_arguments_for(tool, arguments))
        except AgentError as failure:
            # A tool refusing malformed input is still an answer the turn can
            # use, surfaced in Hebrew like everything leaving the backend.
            return _failure(name, str(failure))
        except TypeError:
            # A call missing a required argument is an ordinary way for a
            # model turn to be slightly wrong; a crash would end it.
            return _failure(name, "חסרים פרטים לקריאה לכלי הזה")
        return dict(result, tool=name, ok=result.get("ok", True))


def _failure(name: str, error: str) -> dict:
    return {"tool": name, "ok": False, "error": error}


def _arguments_for(tool: Callable, arguments: dict) -> dict:
    """The subset of `arguments` this tool actually accepts.

    Dropping unknown names turns a slightly-wrong call into a call; the
    tool's own required-argument check still refuses one missing something.
    """
    accepted = set(inspect.signature(tool).parameters) - {"team_id"}
    return {key: value for key, value in arguments.items() if key in accepted}


def _invalid_date_argument(arguments: dict) -> str:
    """Reject relative or ambiguous dates at the shared tool boundary."""
    for key in _DATE_ARGUMENTS:
        value = text(arguments.get(key))
        if not value:
            continue
        try:
            datetime.date.fromisoformat(value)
        except ValueError:
            return key
    return ""
