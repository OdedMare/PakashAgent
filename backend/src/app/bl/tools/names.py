"""Every tool the agent may call, by name, and what each is for."""

# The planner picks from this list and nothing else -- a name outside it is a
# tool that does not exist, and answering it with an error rather than an
# improvisation is what keeps the model from describing capabilities the
# product does not have.
TOOL_READ_PERIOD = "read_period"
TOOL_TEAM_OVERVIEW = "team_overview"
TOOL_EMPLOYEE_STATE = "employee_state"
TOOL_COVERAGE_GAPS = "coverage_gaps"
TOOL_VALIDATE_PLACEMENT = "validate_placement"
TOOL_FIND_REPLACEMENTS = "find_replacements"
TOOL_PUBLISH_READINESS = "publish_readiness"
TOOL_PROFILE_GAPS = "profile_gaps"

TOOL_NAMES = (
    TOOL_READ_PERIOD,
    TOOL_TEAM_OVERVIEW,
    TOOL_EMPLOYEE_STATE,
    TOOL_COVERAGE_GAPS,
    TOOL_VALIDATE_PLACEMENT,
    TOOL_FIND_REPLACEMENTS,
    TOOL_PUBLISH_READINESS,
    TOOL_PROFILE_GAPS,
)

# What each tool is for, in the manager's language rather than the code's.
# Handed to the model as its menu and rendered in the UI as what the agent
# did, so the two can never describe the tools differently.
TOOL_DESCRIPTIONS = {
    TOOL_READ_PERIOD: "קריאת הסידור ומי סוגר בכל סוף שבוע בתקופה",
    TOOL_TEAM_OVERVIEW: "מי נמצא בצוות, מה התפקידים ואילו משמרות הוגדרו",
    TOOL_EMPLOYEE_STATE: "המשמרות, השעות והאילוצים של עובד אחד",
    TOOL_COVERAGE_GAPS: "משמרות שחסרים בהן אנשים",
    TOOL_VALIDATE_PLACEMENT: "בדיקה מה יקרה אם משבצים מישהו למשמרת",
    TOOL_FIND_REPLACEMENTS: "מי יכול לקחת משמרת במקום מישהו אחר",
    TOOL_PUBLISH_READINESS: "מה חסר לפני פרסום התקופה לצוות",
    TOOL_PROFILE_GAPS: "מה הסוכן עדיין לא יודע על מקום העבודה",
}
