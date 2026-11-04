"""כשירות on the setup screen: a dated qualification, kept alive by worked shifts."""

import datetime

import pytest

from app.bl import qualification
from app.bl.audit import audit
from app.bl.audit.unit_policy import qualification_expired
from app.bl.profile_service import ProfileService

TODAY = datetime.date(2026, 11, 4)
POLICY = {"unit_policy": {"qualification_validity_days": 30}}


def person(*rows):
    return {"name": "דנה", "qualifications": [{"role": role, "last_active": last} for role, last in rows]}


def test_an_undated_person_has_no_standing():
    assert qualification.standing(POLICY, {"name": "דנה"}, "2026-11-01", TODAY) is None
    assert qualification.standing(POLICY, person(("אלחוט", "")), "2026-11-01", TODAY) is None


def test_with_no_shift_the_window_runs_from_the_typed_date():
    row = qualification.standing(POLICY, person(("אלחוט", "2026-10-01")), None, TODAY)
    assert row["status"] == "expired"
    assert row["rows"][0]["valid_until"] == "2026-10-31"
    assert row["last_shift"] is None


def test_a_worked_shift_keeps_the_qualification_alive():
    row = qualification.standing(POLICY, person(("אלחוט", "2026-09-01")), "2026-10-20", TODAY)
    assert row["status"] == "valid"
    assert row["rows"][0] == {"role": "אלחוט", "last_active": "2026-10-20",
                              "valid_until": "2026-11-19", "days_left": 15, "status": "valid"}
    assert row["last_shift"] == "2026-10-20"


def test_a_shift_ahead_of_today_has_not_been_worked_yet():
    row = qualification.standing(POLICY, person(("אלחוט", "2026-09-01")), "2026-11-10", TODAY)
    assert row["status"] == "expired" and row["last_shift"] is None


@pytest.mark.parametrize("last, status", [
    ("2026-10-13", "valid"),      # 8 days left
    ("2026-10-12", "expiring"),   # 7 days left
    ("2026-10-05", "expiring"),   # the last day
    ("2026-10-04", "expired"),    # ended yesterday
])
def test_status_bands(last, status):
    assert qualification.standing(POLICY, person(("אלחוט", last)), None, TODAY)["status"] == status


def test_the_worst_role_colours_the_person():
    row = qualification.standing(POLICY, person(("אלחוט", "2026-11-01"), ("נהג", "2026-09-01")), None, TODAY)
    assert row["status"] == "expired"
    assert [r["status"] for r in row["rows"]] == ["valid", "expired"]


def test_the_unit_default_and_an_unsaved_window():
    profile = {}  # 90 days unless the unit says otherwise
    assert qualification.standing(profile, person(("אלחוט", "2026-09-01")), None, TODAY)["status"] == "valid"
    assert qualification.standing(profile, person(("אלחוט", "2026-09-01")), None, TODAY, days=30)["status"] == "expired"


def test_the_audit_counts_a_shift_worked_earlier_in_the_period():
    stale = {"name": "דנה", "qualifications": [{"role": "אלחוט", "last_active": "2026-01-01"}]}
    on = datetime.date(2026, 11, 8)
    assert qualification_expired(POLICY, stale, "אלחוט", on)
    assert not qualification_expired(POLICY, stale, "אלחוט", on, worked=datetime.date(2026, 11, 1))
    assert qualification_expired(POLICY, stale, "אלחוט", on, worked=datetime.date(2026, 9, 1))


def test_the_audit_reports_the_lapse_only_on_the_first_shift_of_a_run():
    shifts = [{"name": "יום", "start_time": "08:00", "end_time": "20:00",
               "staffing": [{"days": [], "headcount": 1, "required_roles": ["אלחוט"]}]}]
    stale = {"name": "דנה", "eligible_shifts": ["יום"], "qualifications": [{"role": "אלחוט", "last_active": "2026-01-01"}]}
    profile = dict(POLICY, employees=[stale], shifts=shifts)
    rows = [{"employee": "דנה", "shift": "יום", "date": d} for d in ("2026-11-08", "2026-11-09")]
    lapsed = [w for w in audit(rows, shifts, [stale], profile=profile) if w["code"] == "qualification_expired"]
    assert [w["date"] for w in lapsed] == ["2026-11-08"]


class _Repo:
    def __init__(self):
        self.asked = None

    def team_profile(self, team_id):
        return POLICY

    def last_shift_dates(self, team_id, through):
        self.asked = (team_id, through)
        return {"דנה": "2026-11-01"}


def test_the_service_reads_shifts_worked_through_today():
    repo = _Repo()
    result = ProfileService(repo).qualifications("team", [person(("אלחוט", "2026-09-01"))], TODAY)
    assert repo.asked == ("team", "2026-11-04")
    assert result["דנה"]["status"] == "valid"
    assert result["דנה"]["rows"][0]["valid_until"] == "2026-12-01"
