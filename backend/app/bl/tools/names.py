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
TOOL_WHO_WORKS = "who_works"
TOOL_WORKLOAD_RANKING = "workload_ranking"
TOOL_WHO_IS_AWAY = "who_is_away"
TOOL_SHADOW_PARTNERS = "shadow_partners"

TOOL_NAMES = (
    TOOL_READ_PERIOD,
    TOOL_TEAM_OVERVIEW,
    TOOL_EMPLOYEE_STATE,
    TOOL_COVERAGE_GAPS,
    TOOL_VALIDATE_PLACEMENT,
    TOOL_FIND_REPLACEMENTS,
    TOOL_PUBLISH_READINESS,
    TOOL_PROFILE_GAPS,
    TOOL_WHO_WORKS,
    TOOL_WORKLOAD_RANKING,
    TOOL_WHO_IS_AWAY,
    TOOL_SHADOW_PARTNERS,
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
    TOOL_FIND_REPLACEMENTS: (
        "מי יכול לקחת משמרת במקום מישהו אחר; חובה לשלוח employee, "
        "shift_name ו-slot_date בפורמט YYYY-MM-DD"
    ),
    TOOL_PUBLISH_READINESS: "מה חסר לפני פרסום התקופה לצוות",
    TOOL_PROFILE_GAPS: "מה הסוכן עדיין לא יודע על מקום העבודה",
    TOOL_WHO_WORKS: "מי משובץ בתאריך או בטווח (day או starts_on+ends_on), לפי תאריך ומשמרת; shift_name מסנן משמרת",
    TOOL_WORKLOAD_RANKING: (
        "מי עשה הכי הרבה (או הכי מעט) משמרות בטווח, ממוין; אפשר לסנן לפי shift_name, "
        "role, או commanders_only למפקדי משמרת; top קובע כמה להחזיר"
    ),
    TOOL_WHO_IS_AWAY: "מי לא נמצא בתאריך או בטווח ולמה: בבית לפי המחזור, או אילוץ שנרשם (חולה, חופש)",
    TOOL_SHADOW_PARTNERS: "מי יכול לחפוף (להדריך) נחפף/ת מסוים/ת, או אילו נחפפים יכולים ללוות עובד/ת מסוים/ת",
}
