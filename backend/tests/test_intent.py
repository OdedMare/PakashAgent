"""Reading a manager's Hebrew sentence with no model.

The product promises it works without an LLM (`README.md`), and this module
is what that promise rests on for the conversational half. Table-driven,
because the whole contract is sentences in and a placement out.

Two properties matter more than any individual match:

- **It never guesses.** A sentence it cannot place is `unknown`, not the
  nearest thing. An agent that acts on a misread sentence with no model to
  blame is worse than one that says it did not follow.
- **Names come from the roster, never from word shape.** A token is an
  employee because the workspace declared it — which is what stops a
  misspelled ordinary word from becoming a person.
"""

import pytest

from app.bl.intent import (
    INTENT_ABSENCE,
    INTENT_EMPLOYEE,
    INTENT_GAPS,
    INTENT_PERIOD,
    INTENT_PUBLISH,
    INTENT_REPLACEMENTS,
    INTENT_UNKNOWN,
    read,
)

MORNING = "בוקר"
EVENING = "צהריים"

DANA = "דנה"
YOSSI = "יוסי"
MAYA = "מאיה"

ROSTER = [DANA, YOSSI, MAYA]
SHIFTS = [MORNING, EVENING]

# A Sunday-to-Saturday week, so a weekday name has somewhere to land.
PERIOD = {"starts_on": "2026-08-16", "ends_on": "2026-08-22"}
TODAY = "2026-08-20"


def _read(text):
    return read(text, ROSTER, SHIFTS, today=TODAY, period=PERIOD)


# -- what each sentence is asking for --------------------------------------


@pytest.mark.parametrize("sentence,expected", [
    ("מי יכול להחליף את יוסי בשבת", INTENT_REPLACEMENTS),
    ("מי יכולה להחליף את דנה", INTENT_REPLACEMENTS),
    ("צריך למצוא כיסוי למשמרת צהריים מחר", INTENT_REPLACEMENTS),
    ("דנה חולה ביום חמישי", INTENT_ABSENCE),
    ("מאיה בחופש בשישי", INTENT_ABSENCE),
    ("יוסי לא מגיע מחר", INTENT_ABSENCE),
    ("מה חסר בסידור", INTENT_GAPS),
    ("איפה חסרים אנשים", INTENT_GAPS),
    ("יש משמרות ריקות?", INTENT_GAPS),
    ("כמה שעות יש למאיה", INTENT_EMPLOYEE),
    ("מתי עובדת דנה", INTENT_EMPLOYEE),
    ("מה חסר לפני פרסום", INTENT_PUBLISH),
    ("אפשר לפרסם את השבוע?", INTENT_PUBLISH),
    ("תראה לי את השבוע", INTENT_PERIOD),
    ("מה הסידור הנוכחי", INTENT_PERIOD),
])
def test_sentences_are_placed(sentence, expected):
    assert _read(sentence)["intent"] == expected


@pytest.mark.parametrize("sentence", [
    "בלה בלה בלה",
    "תודה רבה",
    "מה השעה",
    "",
])
def test_a_sentence_it_cannot_place_is_never_guessed(sentence):
    """The property that makes the fallback safe rather than merely present."""
    answer = read(sentence, ROSTER, SHIFTS, today=TODAY, period=PERIOD)
    assert answer["intent"] == INTENT_UNKNOWN
    assert answer["confident"] is False


def test_absence_is_read_before_replacement():
    """"דנה חולה, מי יכול להחליף" carries the extra fact and must keep it."""
    answer = _read("דנה חולה ביום חמישי, מי יכול להחליף אותה")
    assert answer["intent"] == INTENT_ABSENCE


def test_publish_is_read_before_gaps():
    """"מה חסר לפני פרסום" contains "מה חסר" and is not a bare gap search."""
    assert _read("מה חסר לפני פרסום")["intent"] == INTENT_PUBLISH


# -- names -----------------------------------------------------------------


def test_a_name_is_found_because_the_roster_declares_it():
    assert _read("מי יכול להחליף את יוסי בשבת")["employee"] == YOSSI


def test_a_name_the_roster_does_not_carry_is_not_a_person():
    answer = _read("מי יכול להחליף את רון בשבת")
    assert answer["employee"] == ""


def test_the_longest_matching_name_wins():
    """A roster holding both "דנה" and "דנה כהן" must match the fuller one."""
    answer = read(
        "דנה כהן חולה מחר", [DANA, "דנה כהן"], SHIFTS,
        today=TODAY, period=PERIOD,
    )
    assert answer["employee"] == "דנה כהן"


def test_an_empty_roster_finds_nobody_rather_than_inventing():
    answer = read("דנה חולה מחר", [], SHIFTS, today=TODAY, period=PERIOD)
    assert answer["employee"] == ""


# -- shifts ----------------------------------------------------------------


def test_a_shift_is_found_from_the_declared_vocabulary():
    assert _read("צריך כיסוי למשמרת צהריים מחר")["shift"] == EVENING


def test_a_shift_the_workplace_never_declared_is_not_matched():
    """No literal shift list lives here (D9)."""
    answer = read(
        "מי יכול לקחת את משמרת הלילה", ROSTER, [MORNING],
        today=TODAY, period=PERIOD,
    )
    assert answer["shift"] == ""


# -- dates -----------------------------------------------------------------


def test_a_weekday_resolves_inside_the_open_period():
    """"בשבת" while looking at a week means *that* week's Saturday."""
    assert _read("מי יכול להחליף את יוסי בשבת")["date"] == "2026-08-22"


def test_a_weekday_with_no_period_resolves_against_today():
    answer = read(
        "מי יכול להחליף את יוסי בשבת", ROSTER, SHIFTS, today=TODAY,
    )
    # 2026-08-20 is a Thursday; the coming Saturday is the 22nd.
    assert answer["date"] == "2026-08-22"


@pytest.mark.parametrize("word,expected", [
    ("היום", "2026-08-20"),
    ("מחר", "2026-08-21"),
    ("מחרתיים", "2026-08-22"),
    ("אתמול", "2026-08-19"),
])
def test_relative_days_resolve_against_today(word, expected):
    answer = read(
        "דנה חולה %s" % word, ROSTER, SHIFTS, today="2026-08-20",
    )
    assert answer["date"] == expected


@pytest.mark.parametrize("written,expected", [
    ("2026-08-19", "2026-08-19"),
    ("19/8/2026", "2026-08-19"),
    ("19.8.26", "2026-08-19"),
])
def test_an_explicit_date_is_read_as_written(written, expected):
    """The formats the real source files use, plus the one the API speaks."""
    answer = read(
        "דנה חולה ב-%s" % written, ROSTER, SHIFTS, today=TODAY,
    )
    assert answer["date"] == expected


def test_a_sentence_naming_no_day_carries_no_date():
    assert _read("כמה שעות יש למאיה")["date"] == ""


def test_an_impossible_date_is_dropped_rather_than_invented():
    answer = read("דנה חולה ב-45/13/26", ROSTER, SHIFTS, today=TODAY)
    assert answer["date"] == ""


# -- bounds ----------------------------------------------------------------


def test_a_very_long_sentence_is_bounded():
    answer = read("א" * 5000, ROSTER, SHIFTS, today=TODAY)
    assert len(answer["request"]) <= 500
