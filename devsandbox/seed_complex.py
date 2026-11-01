"""Open a מכלול of משמרות from one unit's scenario, through the public API.

    python devsandbox/seed_complex.py devsandbox/scenarios/unit_619_complex.json \\
        --url http://localhost:8100 --admin-password 010802 \\
        --team-password 619619 --commander-password 619000 --build

The split file names a base scenario (one team's profile) and the משמרות to
cut it into: each takes the soldiers whose role it lists, the shift types it
lists, and any extra soldiers named in `also` (the נחפפים, who have no team
of their own). Everything else in the base -- the day cycle, the rules --
is copied to every משמרת.

For each משמרת it opens a team in the operator console and saves its
profile as its manager, exactly as `seed_scenario.py` does; then it opens
the מכלול over them and issues the commander's password (D43). `--build`
also asks the solver for four weeks from the cycle's anchor in each משמרת.
Standard library only. Development use: it never deletes or overwrites.
"""

import argparse
import datetime
import http.cookiejar
import json
import os
import sys
import urllib.error
import urllib.request


def split(base: dict, units: list) -> list:
    """One profile per משמרת. Refuses a soldier no משמרת takes, or one that
    two take, rather than dropping or duplicating anybody silently."""
    taken = {}  # name -> unit
    profiles = []
    for unit in units:
        people = [
            person for person in base["employees"]
            if person.get("role") in unit["roles"] or person["name"] in unit.get("also", [])
        ]
        shifts = [shift for shift in base["shifts"] if shift["name"] in unit["shifts"]]
        missing = set(unit["shifts"]) - {shift["name"] for shift in shifts}
        if missing:
            sys.exit("לא נמצאו בבסיס סוגי המשמרות: %s" % ", ".join(sorted(missing)))
        for person in people:
            if person["name"] in taken:
                sys.exit("%s שויך גם ל%s וגם ל%s" % (person["name"], taken[person["name"]], unit["name"]))
            taken[person["name"]] = unit["name"]
        workplace = dict(base.get("workplace") or {}, name=unit["name"])
        profiles.append((unit["name"], dict(base, workplace=workplace, employees=people, shifts=shifts)))
    left = [person["name"] for person in base["employees"] if person["name"] not in taken]
    if left:
        sys.exit("לא שויכו לאף משמרת: %s" % ", ".join(left))
    return profiles


class Client:
    def __init__(self, base: str):
        self._base = base.rstrip("/")
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def call(self, method: str, path: str, body: dict) -> dict:
        request = urllib.request.Request(
            self._base + path, data=json.dumps(body).encode("utf-8"), method=method,
            headers={"Content-Type": "application/json"})
        try:
            with self._opener.open(request, timeout=600) as response:
                return json.loads(response.read() or b"{}")
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", "replace")
            sys.exit("%s %s נכשל (%d): %s" % (method, path, error.code, detail))


def build(client: Client, anchor: str) -> str:
    """Four weeks from the Sunday of the cycle's anchor, a week per call."""
    day = datetime.date.fromisoformat(anchor)
    sunday = day - datetime.timedelta(days=(day.weekday() + 1) % 7)
    placed = required = 0
    for week in range(4):
        start = sunday + datetime.timedelta(days=7 * week)
        schedule = client.call("POST", "/api/schedule/generate", {
            "starts_on": start.isoformat(),
            "ends_on": (start + datetime.timedelta(days=6)).isoformat(),
        })
        placed += len(schedule.get("assignments") or [])
        required += sum(int(slot.get("headcount") or 0) for slot in schedule.get("slots") or [])
    return "%d שיבוצים (נחפפים כלולים) מול %d מקומות" % (placed, required)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("split", help="a split file, e.g. scenarios/unit_619_complex.json")
    parser.add_argument("--url", default="http://localhost:8100", help="the backend's base URL")
    parser.add_argument("--admin-password", required=True, help="the operator console password")
    parser.add_argument("--team-password", required=True, help="every משמרת's commander password")
    parser.add_argument("--commander-password", required=True, help="the מפקד מכלול password")
    parser.add_argument("--build", action="store_true", help="build four weeks in every משמרת")
    args = parser.parse_args()

    with open(args.split, encoding="utf-8") as handle:
        plan = json.load(handle)
    with open(os.path.join(os.path.dirname(args.split), plan["base"]), encoding="utf-8") as handle:
        base = json.load(handle)
    profiles = split(base, plan["units"])

    admin = Client(args.url)
    admin.call("POST", "/api/admin/login", {"password": args.admin_password})
    anchor = next(iter((base.get("workplace") or {}).get("day_cycles") or []), {}).get("anchor_date")
    team_ids = []
    for name, profile in profiles:
        team = admin.call("POST", "/api/admin/teams", {"name": name, "password": args.team_password})
        team_ids.append(team["id"])
        manager = Client(args.url)
        manager.call("POST", "/api/workspace/login", {"team_id": team["id"], "password": args.team_password})
        manager.call("PUT", "/api/profile", profile)
        line = "משמרת '%s': %d חיילים, %d סוגי משמרות" % (
            name, len(profile["employees"]), len(profile["shifts"]))
        if args.build and anchor:
            line += " · " + build(manager, anchor)
        print(line)

    complex_row = admin.call("POST", "/api/admin/complexes", {
        "name": plan["complex"], "password": args.commander_password, "team_ids": team_ids,
    })
    print("נפתח המכלול '%s' עם %d משמרות." % (complex_row["name"], len(complex_row["teams"])))
    print("כניסה: 'מפקד משמרת' עם סיסמת המשמרת, או 'מפקד מכלול' עם סיסמת המפקד.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
