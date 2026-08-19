"""Layout inference over the two real files, which disagree structurally.

`BUILD_ORDER.md` calls this the riskiest part of the build, and the reason is
in `FILE_FORMATS.md`: the two samples are not two dialects of one layout,
their axes mean different things. So the test that matters is not "does it
parse Sample A" but **does one inference pass both** — which is why they run
through the same function with the same vocabulary here.

No database and no model: inference is pure grid arithmetic, so this is a
unit test of the whole contract.
"""

import io

import pytest

from app.bl.export import as_workbook
from app.bl.importer import infer, read_grid
from app.common.errors import AgentError
from tests.fixtures.build import EVENING, MORNING, ON_CALL, sample_a, sample_b

PROFILE = {"shifts": [{"name": MORNING}, {"name": EVENING}, {"name": ON_CALL}]}


def _grid(book):
    stream = io.BytesIO()
    book.save(stream)
    return read_grid(stream.getvalue(), "schedule.xlsx")


def _interpret(book, profile=PROFILE):
    return infer(_grid(book), profile)


# -- Sample A: shift-major, dense ------------------------------------------

def test_sample_a_is_read_as_shift_major():
    found = _interpret(sample_a())
    assert found.layout == "shift_major"


def test_sample_a_finds_both_declared_shifts():
    found = _interpret(sample_a())
    assert found.shifts == [MORNING, EVENING]


def test_sample_a_spans_the_whole_week():
    found = _interpret(sample_a())
    assert found.starts_on == "2025-06-15"
    assert found.ends_on == "2025-06-19"


def test_sample_a_is_dense_every_cell_an_assignment():
    """5 dates x 2 shifts, every cell filled."""
    found = _interpret(sample_a())
    assert len(found.assignments) == 10


def test_sample_a_reads_a_named_cell_as_that_persons_assignment():
    found = _interpret(sample_a())
    assert {
        "employee": "שובל ק.", "shift": MORNING, "date": "2025-06-15",
    } in found.assignments


def test_sample_a_weekday_row_is_header_not_data():
    """`ראשון` under the dates is a label; it must not become a shift."""
    found = _interpret(sample_a())
    assert all("ראשון" not in name for name in found.shifts)


def test_sample_a_counts_each_person_once():
    found = _interpret(sample_a())
    assert found.people.count("אלמוג ע.") == 1
    assert len(found.people) == 6


# -- Sample B: person-major, sparse, nested header -------------------------

def test_sample_b_is_read_as_person_major():
    found = _interpret(sample_b())
    assert found.layout == "person_major"


def test_sample_b_reads_the_nested_header_into_three_shifts():
    """The date row is merged across its shift sub-columns."""
    found = _interpret(sample_b())
    assert sorted(found.shifts) == sorted([MORNING, EVENING, ON_CALL])


def test_sample_b_pairs_a_cell_with_the_date_its_column_sits_under():
    found = _interpret(sample_b())
    assert {
        "employee": "מאור נ", "shift": EVENING, "date": "2026-02-03",
    } in found.assignments


def test_sample_b_is_sparse():
    """Three names in a 5x6 grid; the empty cells are not assignments."""
    found = _interpret(sample_b())
    assert len(found.assignments) == 3


def test_sample_b_classifies_an_availability_marker_not_as_a_person():
    """`לא זמינה` shares the grid with names and is not one."""
    found = _interpret(sample_b())
    assert "לא זמינה" not in found.people
    assert not any(
        row["employee"] == "לא זמינה" for row in found.assignments
    )


def test_sample_b_records_the_marker_as_unavailability():
    found = _interpret(sample_b())
    assert len(found.unavailability) == 1
    assert found.unavailability[0]["date"] == "2026-02-03"
    assert found.unavailability[0]["shift"] == EVENING


def test_an_unattributed_marker_is_flagged_rather_than_guessed():
    """Sample B's last lane holds a marker and no name at all.

    The file does not say whose it is, so neither does the importer -- it
    warns instead, and the confirm screen (D7) is where the name is supplied.
    """
    found = _interpret(sample_b())
    assert found.unavailability[0]["employee"] == ""
    assert any("אינם משויכים" in note for note in found.warnings)


def test_a_lane_is_named_by_its_placements_not_its_first_cell():
    """A lane whose name is written where the person is placed.

    Taking the first non-empty cell would make `לא זמינה` a person.
    """
    grid = [
        ["", "2.2", "2.2"],
        ["", MORNING, EVENING],
        ["", "נועה ר", "לא זמינה"],
    ]
    found = infer(grid, PROFILE)
    assert found.unavailability[0]["employee"] == "נועה ר"
    assert "לא זמינה" not in found.people


# -- the point of the whole exercise ---------------------------------------

def test_one_inference_reads_both_structurally_different_files():
    """The regression `FILE_FORMATS.md` exists for.

    Same function, same vocabulary, opposite axis semantics.
    """
    first = _interpret(sample_a())
    second = _interpret(sample_b())
    assert first.layout != second.layout
    assert first.assignments and second.assignments


def test_an_exported_week_can_be_imported_back():
    """`export.py` writes Sample A's shape precisely so this round-trips."""
    schedule = {
        "starts_on": "2026-08-17", "ends_on": "2026-08-18",
        "slots": [
            {"shift_name": MORNING, "slot_date": "2026-08-17"},
            {"shift_name": MORNING, "slot_date": "2026-08-18"},
        ],
        "assignments": [
            {"employee": "דנה", "shift": MORNING, "date": "2026-08-17"},
            {"employee": "יוסי", "shift": MORNING, "date": "2026-08-18"},
        ],
    }
    found = infer(read_grid(as_workbook(schedule), "x.xlsx"), PROFILE)
    assert sorted(found.people) == ["דנה", "יוסי"]
    assert len(found.assignments) == 2


# -- D7: an interpretation is something a person approves ------------------

def test_the_interpretation_summarises_itself_for_confirmation():
    """D7's confirm screen needs one readable sentence."""
    summary = _interpret(sample_a()).summary()
    assert "6 אנשים" in summary
    assert "10 שיבוצים" in summary


def test_unreadable_input_is_refused_in_hebrew():
    with pytest.raises(AgentError):
        infer([], PROFILE)


def test_a_sheet_with_no_dates_is_refused():
    with pytest.raises(AgentError):
        infer([["שם", "משהו"], ["דנה", "אחר"]], PROFILE)


# -- D9: shift names come from the interview, never from a guess -----------

def test_a_shift_outside_the_declared_vocabulary_is_not_invented():
    """A vocabulary of one means only that one is recognised."""
    found = infer(_grid(sample_a()), {"shifts": [{"name": MORNING}]})
    assert found.shifts == [MORNING]


def test_the_declared_spelling_wins_over_the_sheets():
    """A sheet writing `משמרת בוקר` lands on the declared `בוקר`."""
    grid = [
        ["משמרות", "1/6/25", "2/6/25"],
        ["משמרת בוקר", "דנה", "יוסי"],
    ]
    found = infer(grid, {"shifts": [{"name": MORNING}]})
    assert found.shifts == [MORNING]
