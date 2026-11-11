"""A large team is solved in chunks of shifts, alphabetically (D54)."""

from app.bl.solver import chunks, generate_span
from app.bl.solver.problem import Problem, slots_for

NAMES = ["בוקר", "ערב", "לילה", "תורנות"]
TIMES = {"בוקר": ("07:00", "15:00"), "ערב": ("15:00", "23:00"),
         "לילה": ("23:00", "07:00"), "תורנות": ("09:00", "21:00")}


def _profile(people=30, names=NAMES):
    return {
        "workplace": {"name": "יחידה"},
        "employees": [{"name": "עובד %02d" % number} for number in range(people)],
        "shifts": [{"name": name, "start_time": TIMES[name][0], "end_time": TIMES[name][1],
                    "days": [], "staffing": [{"days": [], "headcount": 2, "required_roles": []}]}
                   for name in names],
    }


def _plan(profile, **options):
    slots = slots_for(profile, "2026-09-06", "2026-09-08")
    return chunks.plan(Problem(profile, slots), **options)


def test_a_large_team_is_split_into_alphabetical_pairs_of_shifts():
    assert _plan(_profile()) == [["בוקר", "לילה"], ["ערב", "תורנות"]]


def test_a_smaller_team_or_too_few_shifts_is_solved_whole():
    assert _plan(_profile(people=29)) == []
    assert _plan(_profile(names=NAMES[:3])) == []
    assert _plan(_profile(), min_people=0) == []
    assert _plan(_profile(), size=0) == []


def test_a_shift_left_alone_joins_the_chunk_before_it():
    five = _profile()
    five["shifts"].append(dict(five["shifts"][0], name="אבטחה"))
    assert _plan(five) == [["אבטחה", "בוקר"], ["לילה", "ערב", "תורנות"]]


def test_a_chunked_build_is_one_legal_schedule():
    profile = _profile()
    pin = {"employee": "עובד 00", "shift": "תורנות", "date": "2026-09-06", "reason": "ביקש"}
    stale = {"employee": "עובד 01", "shift": "ערב", "date": "2026-09-06"}
    outside = {"employee": "עובד 02", "shift": "לילה", "date": "2026-09-05"}
    result = generate_span(profile, "2026-09-06", "2026-09-08", time_limit=4, workers=2,
                           required_assignments=[pin], already_scheduled=[stale, outside])
    rows, metrics = result["assignments"], result["metrics"]
    assert [chunk["shifts"] for chunk in metrics["chunks"]] == [["בוקר", "לילה"], ["ערב", "תורנות"]]
    assert len(rows) == 3 * 4 * 2 and metrics["accepted"] == len(rows)
    assert not result["warnings"]
    assert all(row["reason"] for row in rows)
    assert len({(row["employee"], row["shift"], row["date"]) for row in rows}) == len(rows)
    assert [row["reason"] for row in rows if row["employee"] == "עובד 00"
            and row["shift"] == "תורנות" and row["date"] == "2026-09-06"] == ["ביקש"]
    # The pin on a later chunk's shift stood while the first chunk was solved,
    # and a night worked the day before the span counts for rest in it.
    first_day = {(row["employee"], row["shift"]) for row in rows if row["date"] == "2026-09-06"}
    assert ("עובד 00", "בוקר") not in first_day and ("עובד 02", "בוקר") not in first_day
    # Nobody is placed twice on a day across chunks while thirty people are free.
    days = [(row["employee"], row["date"]) for row in rows]
    assert len(set(days)) == len(days)
    assert metrics["solver_ms"] == sum(chunk["solver_ms"] for chunk in metrics["chunks"])
    assert set(metrics["phases"]) == {"coverage", "balance"}


def test_chunking_can_be_turned_off():
    result = generate_span(_profile(), "2026-09-06", "2026-09-06", time_limit=2, workers=2,
                           chunk_people=0)
    assert "chunks" not in result["metrics"]
    assert len(result["assignments"]) == 8


def test_each_chunk_is_named_and_handed_over_as_it_is_solved():
    from app.common.activity import track_activity
    said, landed = [], []
    pin = {"employee": "עובד 00", "shift": "בוקר", "date": "2026-09-06", "reason": "ביקש"}
    with track_activity(said.append):
        result = generate_span(_profile(), "2026-09-06", "2026-09-06", time_limit=2, workers=2,
                               required_assignments=[pin],
                               on_chunk=lambda shifts, rows: landed.append((shifts, rows)))
    assert said == ["משבצים את המשמרות בוקר, לילה (חלק 1 מתוך 2)…",
                    "משבצים את המשמרות ערב, תורנות (חלק 2 מתוך 2)…"]
    # Every chunk but the last: the whole answer follows it at once.
    assert [shifts for shifts, _ in landed] == [["בוקר", "לילה"]]
    rows = landed[0][1]
    assert len(rows) == 4 and {row["shift"] for row in rows} == {"בוקר", "לילה"}
    assert pin["employee"] in {row["employee"] for row in rows if row["shift"] == "בוקר"}
    assert all(row in result["assignments"] for row in rows)


def test_a_running_build_puts_each_chunk_on_the_board_before_the_next():
    from tests.test_schedule_api import TEAM, _build_app, _client
    app, repo = _build_app()
    repo.profiles[TEAM] = _profile()
    client = _client(app)
    started = client.post("/api/schedule/generate/start", json={
        "starts_on": "2026-09-06", "ends_on": "2026-09-06"}).json()
    writes, write = [], repo.replace_span_assignments

    def recording(schedule_id, team_id, dates, assignments, shifts=None):
        writes.append((shifts, len(assignments)))
        return write(schedule_id, team_id, dates, assignments, shifts=shifts)

    repo.replace_span_assignments = recording
    finished = client.post("/api/schedule/generate/%s/next" % started["id"]).json()
    # The first chunk's two shifts land on their own, then the whole day.
    assert writes == [(["בוקר", "לילה"], 4), (None, 8)]
    assert finished["generation"]["status"] == "complete"
    placed = [(row["employee"], row["shift"]) for row in finished["assignments"]]
    assert len(placed) == 8 and len(set(placed)) == 8
