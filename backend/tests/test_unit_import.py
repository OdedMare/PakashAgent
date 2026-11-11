"""Unit extraction reuses schedule reading without persisting schedules."""

import io

from openpyxl import Workbook

from app.bl.importer.unit import preview_unit
from tests.test_schedule_api import SECRET, TEAM, _build_app, _client
from app.api.dependencies import Guards
from app.api.routers import profile as profile_router
from app.bl.profile_service import ProfileService
from app.common.sessions import ROLE_MEMBER


def workbook(sheets):
    book = Workbook()
    book.remove(book.active)
    for name, rows in sheets.items():
        sheet = book.create_sheet(name)
        for row in rows:
            sheet.append(row)
    stream = io.BytesIO()
    book.save(stream)
    return stream.getvalue()


def test_lists_without_dates_and_multiple_sheets_deduplicate_exact_names_only():
    content = workbook({
        "חיילים": [["שם מלא"], ["דני כהן"], ["דני  כהן"], ["ד. כהן"], ["בית"]],
        "משמרות": [["שם משמרת"], ["בוקר"], ["לילה"], ["07:00-15:00"]],
    })
    result = preview_unit(content, "unit.xlsx", {"employees": [{"name": "דני כהן"}]})
    assert [p["name"] for p in result["people"]] == ["דני כהן", "ד. כהן"]
    assert result["people"][0]["existing"] == "דני כהן"
    assert result["people"][1]["existing"] == ""
    assert "דני כהן" in result["people"][1]["candidates"]
    hours = next(s for s in result["shifts"] if s["name"] == "07:00-15:00")
    assert (hours["start_time"], hours["end_time"], hours["hours_source"]) == ("07:00", "15:00", "file")
    assert len(result["sheets"]) == 2


def test_roster_includes_blank_rows_and_reads_nested_shift_headers():
    content = workbook({"נובמבר": [
        ["2/11/26", "2/11/26", "3/11/26", "3/11/26", ""],
        ["בוקר", "לילה", "בוקר", "לילה", "שם"],
        ["דנה כהן", "", "דנה כהן", "", "דנה כהן"],
        ["יוסי לוי", "", "יוסי לוי", "", "יוסי לוי"],
        ["", "בית", "", "", "רוני ישראלי"],
    ]})
    result = preview_unit(content, "unit.xlsx")
    assert {p["name"] for p in result["people"]} == {"דנה כהן", "יוסי לוי", "רוני ישראלי"}
    shifts = {s["name"]: s for s in result["shifts"]}
    assert set(shifts) == {"בוקר", "לילה"}
    assert shifts["בוקר"]["headcount"] == 2
    assert "assignments" not in result


def test_shift_major_schedule_extracts_new_people_and_modal_headcount():
    content = workbook({"שבוע": [
        ["", "2/11/26", "3/11/26", "4/11/26"],
        ["בוקר", "דנה כהן\nיוסי לוי", "דנה כהן\nיוסי לוי", "דנה כהן"],
    ]})
    result = preview_unit(content, "unit.xlsx")
    assert {p["name"] for p in result["people"]} == {"דנה כהן", "יוסי לוי"}
    assert result["shifts"][0]["headcount"] == 2
    assert result["shifts"][0]["counts"] == [1, 2]


def test_preview_is_manager_only_and_writes_nothing_even_before_setup():
    app, repo = _build_app()
    repo.profiles.pop(TEAM)
    app.include_router(profile_router.build_router(ProfileService(repo), Guards(SECRET)))
    content = workbook({"צוות": [["שם"], ["דנה כהן"]]})
    before = dict(repo.schedules)
    response = _client(app).post("/api/profile/import/preview", files={"file": ("unit.xlsx", content)})
    assert response.status_code == 200, response.text
    assert response.json()["people"][0]["name"] == "דנה כהן"
    assert repo.schedules == before and repo.model_calls == []
    assert TEAM not in repo.profiles
    denied = _client(app, role=ROLE_MEMBER).post("/api/profile/import/preview", files={"file": ("unit.xlsx", content)})
    assert denied.status_code in (401, 403)


def test_unrecognized_sheet_stays_available_for_manual_completion():
    result = preview_unit(workbook({"הוראות": [["הסבר כללי"]]}), "unit.xlsx")
    assert not result["people"] and not result["shifts"]
    assert not result["sheets"][0]["recognized"]
    assert result["warnings"]


def test_explicit_shift_hours_win_over_defaults_without_changing_existing_profile():
    content = workbook({"משמרות": [["משמרת", "התחלה", "סיום"], ["בוקר", "07:30", "15:30"]]})
    existing = {"name": "בוקר", "start_time": "08:00", "end_time": "16:00", "headcount": 4}
    result = preview_unit(content, "unit.xlsx", {"shifts": [existing]})
    shift = result["shifts"][0]
    assert (shift["start_time"], shift["end_time"], shift["hours_source"]) == ("07:30", "15:30", "file")
    assert shift["existing"] == existing and existing["start_time"] == "08:00"
