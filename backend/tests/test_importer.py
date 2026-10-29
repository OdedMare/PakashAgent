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
