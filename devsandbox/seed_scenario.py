"""Open a team pre-loaded with a scenario profile, through the public API.

    python devsandbox/seed_scenario.py devsandbox/scenarios/unit_619.json \
        --url http://localhost:8100 --admin-password 010802 --team-password 619619

Opens the team from the operator console (`/api/admin/teams`), signs in to
it as its manager, and saves the scenario with `PUT /api/profile` -- the same
calls the screens make, so the profile goes through every validator a hand-
built one would. Standard library only, so it runs from any machine that can
reach the backend. Development use: it never deletes or overwrites a team.
"""

import argparse
import http.cookiejar
import json
import sys
import urllib.error
import urllib.request


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("scenario", help="a profile JSON file, e.g. scenarios/unit_619.json")
    parser.add_argument("--url", default="http://localhost:8100", help="the backend's base URL")
    parser.add_argument("--admin-password", required=True, help="the operator console password")
    parser.add_argument("--team-password", required=True, help="the new team's manager password")
    parser.add_argument("--name", help="the team's name; defaults to the scenario's unit name")
    args = parser.parse_args()

    with open(args.scenario, encoding="utf-8") as handle:
        profile = json.load(handle)
    name = args.name or profile.get("workplace", {}).get("name") or "סימולציה"
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    base = args.url.rstrip("/")

    def call(method: str, path: str, body: dict) -> dict:
        request = urllib.request.Request(
            base + path, data=json.dumps(body).encode("utf-8"), method=method,
            headers={"Content-Type": "application/json"})
        try:
            with opener.open(request) as response:
                return json.loads(response.read() or b"{}")
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", "replace")
            sys.exit("%s %s נכשל (%d): %s" % (method, path, error.code, detail))

    call("POST", "/api/admin/login", {"password": args.admin_password})
    team = call("POST", "/api/admin/teams", {"name": name, "password": args.team_password})
    call("POST", "/api/workspace/login", {"team_id": team["id"], "password": args.team_password})
    call("PUT", "/api/profile", profile)
    print("נפתח הצוות '%s' (%s) עם %d אנשי צוות ו-%d משמרות."
          % (name, team["id"], len(profile.get("employees") or []),
             len(profile.get("shifts") or [])))
    print("כניסה: בחרו את הצוות במסך הכניסה והזינו את סיסמת המנהל שנבחרה.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
