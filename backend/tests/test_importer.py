"""The importer reads a schedule in whatever shape the workplace kept it.

Each test is a shape a real manager writes: the two samples in
`docs/FILE_FORMATS.md`, each turned on its side, people down the side with
shift names in the cells, weekday templates, stacked weeks, titles and
totals around the grid. None of them has code of its own -- they are all a
`Layout`, found by detection, by the model, or by the manager.
"""

import io
import json

import pytest
from openpyxl import Workbook

from app.bl.importer import LayoutMapper, infer, read_grids
from app.bl.importer.roster import AMBIGUOUS, EXACT, MATCHED, UNKNOWN, match_people
from app.common.errors import AgentError

MORNING, NOON, NIGHT = "בוקר", "צהריים", "כונן לילה"

PROFILE = {
    "employees": [{"name": name} for name in (
        "שובל קרמר", "אלמוג עזרא", "אורי אבן", "תאיר גל", "ניצן שמש", "סאלי אור")],
    "shifts": [
        {"name": MORNING, "start_time": "07:00", "end_time": "15:00"},
        {"name": NOON, "start_time": "15:00", "end_time": "23:00"},
        {"name": NIGHT, "start_time": "23:00", "end_time": "07:00"},
    ],
}

SAMPLE_A = [
    ["סידור עבודה", "", "", ""],
    ["", "", "", ""],
    ["", "15/6/25", "16/6/25", "17/6/25"],
    ["משמרות", "ראשון", "שני", "שלישי"],
    [MORNING, "שובל ק.", "אלמוג ע.", "אורי א."],
    [NOON, "ניצן ש.", "ניצן ש.", "אלמוג ע."],
]

SAMPLE_B = [
    ["", "2.2 ראשון", "2.2 ראשון", "2.2 ראשון", "3.2 שני", "3.2 שני", "3.2 שני"],
    ["", MORNING, NOON, NIGHT, MORNING, NOON, NIGHT],
    ["", "", "ניצן ש", "", "", "ניצן ש", ""],
    ["", "תאיר ג", "", "", "", "", "לא זמינה"],
]


def _turned(grid):
    width = max(len(row) for row in grid)
    return [[row[column] if column < len(row) else "" for row in grid]
            for column in range(width)]


def _rows(result):
    return sorted((row["employee"], row["shift"], row["date"]) for row in result["assignments"])


SAMPLE_A_ROWS = sorted([
    ("שובל קרמר", MORNING, "2025-06-15"), ("אלמוג עזרא", MORNING, "2025-06-16"),
    ("אורי אבן", MORNING, "2025-06-17"), ("ניצן שמש", NOON, "2025-06-15"),
    ("ניצן שמש", NOON, "2025-06-16"), ("אלמוג עזרא", NOON, "2025-06-17"),
])


# -- shapes ------------------------------------------------------------------

def test_sample_a_is_read_with_abbreviated_names_resolved_to_the_roster():
    result = infer(SAMPLE_A, PROFILE)
    assert _rows(result) == SAMPLE_A_ROWS
    assert result["layout"]["lanes"] == "shifts"
    assert result["layout_source"] == "detected"
    assert result["confidence"] >= 0.9


def test_sample_a_on_its_side_reads_the_same_rows():
    result = infer(_turned(SAMPLE_A), PROFILE)
    assert _rows(result) == SAMPLE_A_ROWS
    assert result["layout"]["orientation"] == "dates_down"


def test_sample_b_reads_the_nested_header_and_the_marker_with_its_owner():
    result = infer(SAMPLE_B, PROFILE)
    assert result["layout"]["shift_line"] == 1
    assert ("תאיר גל", MORNING) in [(row[0], row[1]) for row in _rows(result)]
    assert [(row["employee"], row["shift"]) for row in result["unavailability"]] == [
        ("תאיר גל", NIGHT)]
    assert any("ללא שנה" in warning for warning in result["warnings"])


def test_sample_b_on_its_side_reads_the_same_rows():
    assert _rows(infer(_turned(SAMPLE_B), PROFILE)) == _rows(infer(SAMPLE_B, PROFILE))


def test_people_down_the_side_with_the_shift_written_in_each_cell():
    grid = [
        ["שם", "1/11/26", "2/11/26", "3/11/26"],
        ["שובל קרמר", MORNING, "", NOON],
        ["אלמוג עזרא", "07:00-15:00", "חופש", MORNING],
    ]
    result = infer(grid, PROFILE)
    assert result["layout"]["lanes"] == "people"
    assert _rows(result) == sorted([
        ("שובל קרמר", MORNING, "2026-11-01"), ("שובל קרמר", NOON, "2026-11-03"),
        ("אלמוג עזרא", MORNING, "2026-11-01"), ("אלמוג עזרא", MORNING, "2026-11-03"),
    ])
    assert result["unavailability"][0]["employee"] == "אלמוג עזרא"


def test_dates_down_the_side_and_people_across_the_top():
    grid = [
        ["תאריך", "שובל קרמר", "תאיר גל"],
        ["1.11.2026", MORNING, NOON],
        ["2.11.2026", NOON, ""],
    ]
    result = infer(grid, PROFILE)
    assert result["layout"]["orientation"] == "dates_down"
    assert ("תאיר גל", NOON, "2026-11-01") in _rows(result)
    assert len(result["assignments"]) == 3


def test_a_weekday_template_is_laid_on_the_week_the_manager_names():
    grid = [["", "ראשון", "שני", "ג׳"], [MORNING, "שובל", "תאיר", "סאלי"]]
    result = infer(grid, PROFILE, week_start="2026-11-08")
    assert [row["date"] for row in result["assignments"]] == [
        "2026-11-08", "2026-11-09", "2026-11-10"]
    assert result["assumed_week"] == "2026-11-08"


def test_weeks_stacked_on_one_sheet_restart_the_dates():
    grid = [
        ["", "1/11/26", "2/11/26"],
        [MORNING, "שובל קרמר", "תאיר גל"],
        ["", "", ""],
        ["", "8/11/26", "9/11/26"],
        [MORNING, "סאלי אור", "אורי אבן"],
    ]
    result = infer(grid, PROFILE)
    assert result["dates"] == ["2026-11-01", "2026-11-02", "2026-11-08", "2026-11-09"]
    assert "8/11/26" not in [row["employee"] for row in result["assignments"]]


def test_several_people_in_one_cell_are_each_placed():
    grid = [["", "1/11/26"], [MORNING, "שובל קרמר, תאיר גל"]]
    assert len(infer(grid, PROFILE)["assignments"]) == 2


# -- the manager's corrections -----------------------------------------------

def test_a_layout_the_manager_sends_is_read_as_given():
    layout = {"orientation": "dates_across", "header": 2, "lanes": "shifts"}
    result = infer(SAMPLE_A, PROFILE, layout=layout)
    assert result["layout_source"] == "manager"
    assert _rows(result) == SAMPLE_A_ROWS


def test_a_name_can_be_mapped_to_someone_or_left_out():
    grid = [["", "1/11/26", "2/11/26"], [MORNING, "דני", "מישהו"]]
    result = infer(grid, PROFILE, names={"דני": "אורי אבן", "מישהו": ""})
    assert _rows(result) == [("אורי אבן", MORNING, "2026-11-01")]
    statuses = {row["name"]: row["status"] for row in result["people"]}
    assert statuses == {"דני": "mapped", "מישהו": "skipped"}


def test_a_shift_heading_can_be_mapped_to_a_declared_shift():
    grid = [["", "1/11/26"], ["משמרת א", "שובל קרמר"]]
    result = infer(grid, PROFILE, shifts={"משמרת א": MORNING})
    assert _rows(result) == [("שובל קרמר", MORNING, "2026-11-01")]


def test_an_unknown_name_is_kept_and_named_in_the_warnings():
    result = infer([["", "1/11/26"], [MORNING, "זר גמור"]], PROFILE)
    assert result["people"][0]["status"] == UNKNOWN
    assert any("זר גמור" in warning for warning in result["warnings"])


def test_alternative_readings_travel_with_the_answer():
    assert infer(SAMPLE_A, PROFILE)["alternatives"]


# -- the model ------------------------------------------------------------------

class _Mapper:
    def __init__(self, answer):
        self.answer = answer
        self.calls = []

    def propose(self, grid, profile, hint="", previous=None):
        self.calls.append({"hint": hint, "previous": previous})
        return self.answer


def test_the_model_is_not_asked_when_detection_is_sure():
    mapper = _Mapper(None)
    infer(SAMPLE_A, PROFILE, mapper=mapper)
    assert mapper.calls == []


def test_a_hint_asks_the_model_and_its_layout_wins_when_it_reads_better():
    # Dates in a column the detector never looks at as a header (row 13).
    grid = [[""] * 3 for _ in range(13)] + [["", "1/11/26", "2/11/26"],
                                            [MORNING, "שובל קרמר", "תאיר גל"]]
    mapper = _Mapper({"orientation": "dates_across", "header": 13, "lanes": "shifts",
                      "explanation": "תאריכים בשורה 14"})
    result = infer(grid, PROFILE, mapper=mapper)
    assert result["layout_source"] == "model"
    assert result["explanation"] == "תאריכים בשורה 14"
    assert len(result["assignments"]) == 2


def test_a_model_layout_that_reads_worse_than_detection_is_not_used():
    mapper = _Mapper({"orientation": "dates_down", "header": 0, "lanes": "none",
                      "explanation": "x"})
    result = infer(SAMPLE_A, PROFILE, mapper=mapper, hint="קובץ רגיל")
    assert mapper.calls and result["layout_source"] == "detected"


def test_nothing_readable_is_a_hebrew_error():
    with pytest.raises(AgentError):
        infer([["שלום", "עולם"]], PROFILE)


# -- names and files -----------------------------------------------------------

def test_names_match_by_words_and_initials_and_never_guess():
    profile = {"employees": [{"name": "שובל קרמר"}, {"name": "דנה קרמר"}]}
    found = match_people(["שובל קרמר", "שובל ק.", "קרמר", "יוסי"], profile)
    assert found["שובל קרמר"]["status"] == EXACT
    assert found["שובל ק."] == {"employee": "שובל קרמר", "status": MATCHED,
                                "candidates": ["שובל קרמר"]}
    assert found["קרמר"]["status"] == AMBIGUOUS
    assert found["יוסי"]["status"] == UNKNOWN


def test_every_visible_sheet_of_a_workbook_is_returned_with_merges_filled():
    book = Workbook()
    book.active.title = "הוראות"
    book.active["A1"] = "קרא אותי"
    sheet = book.create_sheet("שבוע")
    sheet.append(["", "1/11/26", ""])
    sheet.merge_cells("B1:C1")
    sheet.append(["", MORNING, NOON])
    buffer = io.BytesIO()
    book.save(buffer)
    grids = read_grids(buffer.getvalue(), "file.xlsx")
    assert [title for title, _grid in grids] == ["הוראות", "שבוע"]
    assert grids[1][1][0] == ["", "1/11/26", "1/11/26"]


def test_a_csv_in_the_hebrew_windows_encoding_is_read():
    data = ",1/11/26\n%s,שובל קרמר\n" % MORNING
    grids = read_grids(data.encode("cp1255"), "week.csv")
    assert _rows(infer(grids[0][1], PROFILE)) == [("שובל קרמר", MORNING, "2026-11-01")]


def test_a_short_roster_name_matches_whole_words_only():
    profile = {"employees": [{"name": "יוסי"}, {"name": "דן"}]}
    found = match_people(["יוסי ב.", "דנה כהן"], profile)
    assert found["יוסי ב."]["employee"] == "יוסי"
    assert found["דנה כהן"]["status"] == UNKNOWN


class _Llm:
    def __init__(self, answer):
        self.answer = answer
        self.calls = []

    def complete_json(self, system, user, schema=None, flow=""):
        self.calls.append({"user": json.loads(user), "flow": flow, "schema": schema})
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


def test_the_mapper_sends_the_sheets_corner_and_asks_for_a_layout_only():
    llm = _Llm({"orientation": "dates_down", "header": 0, "lanes": "people",
                "explanation": "עובדים בעמודות", "_usage": {"total_tokens": 9}})
    answer = LayoutMapper(llm).propose(SAMPLE_A, PROFILE, hint="קובץ ישן")
    sent = llm.calls[0]
    assert sent["flow"] == "import"
    assert sent["user"]["sheet"][0] == {"row": 0, "cells": ["סידור עבודה"]}
    assert sent["user"]["hint"] == "קובץ ישן"
    assert "assignments" not in sent["schema"]["properties"]
    assert "_usage" not in answer and answer["lanes"] == "people"


def test_an_unreachable_model_leaves_the_mapper_silent():
    assert LayoutMapper(_Llm(AgentError("down"))).propose(SAMPLE_A, PROFILE) is None
    assert LayoutMapper(_Llm({"orientation": "sideways"})).propose(SAMPLE_A, PROFILE) is None


def test_a_cross_in_a_persons_lane_is_a_day_off_not_a_shift():
    grid = [["שם", "1/11/26", "2/11/26"], ["שובל קרמר", MORNING, "X"]]
    result = infer(grid, PROFILE)
    assert _rows(result) == [("שובל קרמר", MORNING, "2026-11-01")]
    assert result["unavailability"][0]["date"] == "2026-11-02"


# -- the unit's own file: names down column A, each date merged over its
# three shifts, a weekday row and a shift row under it, "בית" across a home
# stretch, a first name where the person works, "-חפיפה" on a handover.

UNIT_NAMES = ("שובל קרמר", "אלמוג עזרא", "אורי אבן", "תאיר גל")
UNIT_SHIFTS = (MORNING, NOON, NIGHT)
DAY_NAMES = ("ראשון", "שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת")


def _unit_file(dates, title_rows=0):
    """`dates` are the header texts, one per day, as the file writes them."""
    header = [""] + [text for text in dates for _shift in UNIT_SHIFTS]
    weekday = [""] + [DAY_NAMES[i % 7] for i in range(len(dates)) for _shift in UNIT_SHIFTS]
    shifts = ["שם"] + list(UNIT_SHIFTS) * len(dates)
    lanes = [[name] + [""] * (3 * len(dates)) for name in UNIT_NAMES]
    lanes[0][1] = "שובל"                      # works the first morning
    lanes[1][2] = "אלמוג-חפיפה"               # a handover, first noon
    lanes[2][1:4] = ["בית", "בית", "בית"]      # home the whole first day
    lanes[3][6] = "תאיר"                      # second day, night
    return [[""] * len(header)] * title_rows + [header, weekday, shifts] + lanes


UNIT_ROWS = [("אלמוג עזרא", NOON), ("שובל קרמר", MORNING), ("תאיר גל", NIGHT)]


def test_the_units_file_with_israeli_dates():
    result = infer(_unit_file(["06/10/2024", "07/10/2024"]), PROFILE)
    assert result["layout"]["lanes"] == "people" and result["layout"]["shift_line"] == 2
    assert [(row[0], row[1]) for row in _rows(result)] == UNIT_ROWS
    assert _rows(result)[2][2] == "2024-10-07"
    assert result["confidence"] >= 0.9


def test_american_dates_are_read_month_first_from_the_line_itself():
    # 10/12 alone could be either; 10/13 settles the whole line.
    result = infer(_unit_file(["10/12/2024", "10/13/2024"]), PROFILE)
    assert result["dates"] == ["2024-10-12", "2024-10-13"]


def test_an_ambiguous_line_is_read_whichever_way_its_dates_run_on():
    result = infer(_unit_file(["10/01/2024", "10/02/2024"]), PROFILE)
    assert result["dates"] == ["2024-10-01", "2024-10-02"]


def test_dates_in_the_second_row_under_a_title_row():
    result = infer(_unit_file(["22.12.2024", "23.12.2024"], title_rows=1), PROFILE)
    assert result["layout"]["header"] == 1
    assert [(row[0], row[1]) for row in _rows(result)] == UNIT_ROWS


def test_home_is_an_absence_and_a_handover_is_a_note_not_a_name():
    result = infer(_unit_file(["06/10/2024", "07/10/2024"]), PROFILE)
    home = [row for row in result["unavailability"] if row["employee"] == "אורי אבן"]
    assert len(home) == 3 and {row["reason"] for row in home} == {"בית"}
    handover = [row for row in result["assignments"] if row["employee"] == "אלמוג עזרא"]
    assert handover[0]["reason"] == "חפיפה"


def test_a_year_on_one_sheet_opens_on_one_month_and_a_window_picks_another():
    import datetime as dt

    days = [dt.date(2024, 1, 1) + dt.timedelta(days=n) for n in range(366)]
    grid = _unit_file([day.strftime("%d/%m/%Y") for day in days])
    grid[-1][-1] = "תאיר"                     # the last night of the year
    shown = infer(grid, PROFILE)
    assert len(shown["dates"]) <= 31 and shown["file_ends_on"] == "2024-12-31"
    assert any("מוצגים רק" in warning for warning in shown["warnings"])
    chosen = infer(grid, PROFILE, date_from="2024-01-01", date_to="2024-01-02")
    assert [(row[0], row[1]) for row in _rows(chosen)] == UNIT_ROWS
