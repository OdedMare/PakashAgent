"""The words the keyword reader recognises, and the shapes they map to."""

# What the manager was asking for. Each maps to one or two `bl/tools.py`
# calls -- the mapping lives in the service, because which period a tool
# should read is a question about stored state rather than about the words.
INTENT_REPLACEMENTS = "replacements"
INTENT_ABSENCE = "absence"
INTENT_GAPS = "gaps"
INTENT_EMPLOYEE = "employee"
INTENT_PUBLISH = "publish_readiness"
INTENT_PERIOD = "period"
INTENT_TEAM = "team"
INTENT_UNKNOWN = "unknown"

# Hebrew weekdays as the product writes them everywhere else -- the interview
# collects them, `audit.py` prints them, the source files use them. Sunday is
# index 0 because the Israeli week runs ראשון through שבת, the same basis
# `week_bounds()` and `useBoard.sundayOf()` are built on.
WEEKDAYS = {
    "ראשון": 0, "יום ראשון": 0, "א'": 0,
    "שני": 1, "יום שני": 1, "ב'": 1,
    "שלישי": 2, "יום שלישי": 2, "ג'": 2,
    "רביעי": 3, "יום רביעי": 3, "ד'": 3,
    "חמישי": 4, "יום חמישי": 4, "ה'": 4,
    "שישי": 5, "יום שישי": 5, "ו'": 5,
    "שבת": 6, "יום שבת": 6, "ש'": 6,
}

# Phrases that say the manager wants somebody else on a shift.
REPLACEMENT_WORDS = (
    "מי יכול להחליף", "מי יכולה להחליף", "להחליף את", "מחליף ל",
    "מחליפה ל", "מי מחליף", "מי מחליפה", "החלפה ל", "מי פנוי", "מי פנויה",
    "מי יכול לקחת", "כיסוי ל", "למצוא כיסוי", "תמצא כיסוי",
)

# Phrases that say somebody is not coming. Read as "find replacements",
# because a manager who says דנה is sick is telling you about a hole.
ABSENCE_WORDS = (
    "חולה", "חולות", "בחופש", "בחופשה", "לא מגיע", "לא מגיעה",
    "לא יכול", "לא יכולה", "לא זמין", "לא זמינה", "מילואים", "חופש",
)

# Phrases asking what is unstaffed.
GAP_WORDS = (
    "מה חסר", "מי חסר", "חסרים", "חסרות", "משמרות ריקות", "ריקות",
    "לא מאויש", "לא מאוישות", "חורים בסידור", "פערים", "כיסוי",
)

# Phrases asking whether the period can go out to the team.
PUBLISH_WORDS = (
    "לפני פרסום", "לפני שאני מפרסם", "לפני שנפרסם", "אפשר לפרסם",
    "מוכן לפרסום", "מוכנה לפרסום", "לפרסם",
)

# Phrases asking to see the period itself.
PERIOD_WORDS = (
    "מה יש השבוע", "תראה לי את השבוע", "איך נראה השבוע", "הסידור של השבוע",
    "מה הסידור", "תראה את הסידור", "הסידור הנוכחי",
)

# Phrases asking about one person's own week.
EMPLOYEE_WORDS = (
    "כמה שעות", "מה יש ל", "מתי עובד", "מתי עובדת", "המשמרות של",
    "השעות של", "מה המצב של", "מה התפקיד של",
)

TEAM_WORDS = (
    "מי בצוות", "מי נמצא בצוות", "רשימת הצוות", "כמה עובדים בצוות",
    "איזה עובדים בצוות", "איזה עובדות בצוות", "מידע על הצוות",
    "ספר לי על הצוות", "מה אתה יודע על הצוות", "מה ידוע על הצוות",
    "התפקיד של כל אחד", "מה הכללים", "אילו כללים", "כללי הצוות",
)

MAX_TEXT_CHARS = 500
