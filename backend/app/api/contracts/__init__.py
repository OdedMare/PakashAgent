"""Pydantic HTTP contracts. No business logic — shapes only.

One module per area of the API; everything is re-exported here so
routers import from `app.api.contracts` as before.
"""

from app.api.contracts.admin import (  # noqa: F401
    AdminCreateTeamRequest,
    AdminDeleteRequest,
    AdminLoginRequest,
    AdminPasswordRequest,
    AdminReleaseRequest,
    AdminUpdateTeamRequest,
)
from app.api.contracts.settings import (  # noqa: F401
    ModelsProbeRequest,
)
from app.api.contracts.workspace import (  # noqa: F401
    CreateTeamRequest,
    LoginRequest,
    PasswordChangeRequest,
    TeamView,
    Workspace,
)
from app.api.contracts.schedule import (  # noqa: F401
    Assignment,
    ClosingGroup,
    Closure,
    GenerationDay,
    GenerationProgress,
    Schedule,
    SchedulePeriod,
    ScheduleProgress,
    Slot,
    Warning,
)
from app.api.contracts.management import (  # noqa: F401
    ChangeEntry,
    Constraint,
    ConstraintPressure,
    Coverage,
    DayLoad,
    EmployeeLoad,
    ManagementOverview,
    ShiftLoad,
    ShiftStats,
    WarningCount,
)
from app.api.contracts.profile import (  # noqa: F401
    ProfileUpdate,
)
from app.api.contracts.generation import (  # noqa: F401
    BlankRequest,
    GenerateDayRequest,
    GenerateRangeRequest,
    GenerateRequest,
    RequiredAssignment,
)
from app.api.contracts.changes import (  # noqa: F401
    ApplyRequest,
    Operation,
    ProfileOperation,
    Proposal,
    ProposeRequest,
)
from app.api.contracts.placement import (  # noqa: F401
    AlternativeEmployee,
    AlternativeSlot,
    Alternatives,
    AssignRequest,
    CheckRequest,
    ClearRequest,
    ConstraintRequest,
    Departure,
    DepartureRequest,
    MoveRequest,
    PlacementCandidate,
    PlacementCheck,
    UnassignRequest,
)
from app.api.contracts.employee import (  # noqa: F401
    ClaimRequest,
    ConstraintSubmission,
    EmployeeLoginRequest,
    EmployeeSignInRequest,
    ReleaseRequest,
    RequestDecision,
    SwapAnswer,
    SwapProposal,
)
from app.api.contracts.preferences import (  # noqa: F401
    Preference,
    PreferenceRequest,
    PreferenceUpdate,
)
