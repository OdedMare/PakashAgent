"""בונה את צוות האלחוט — מגן מרכבה במערכת משמרות זהב.

הסקריפט לא משבץ משמרות. הוא פותח צוות במערכת ומגדיר בו:
  * את האנשים — תפקיד אלחוט, תא, סוג שירות, כשירות (הערות רק למי שלא זמין)
  * את סוגי המשמרות — לכל תא בוקר 08:00-20:00 ולילה 20:00-08:00, עם התקינה מהלוח
  * את הסבב — סדיר, אע"צ והצ"ח 12/2; מילואים עד 4 ימים בשבוע
  * אילוץ אחד: מי שחסום, לא יכול להגיע או לא בפול — לא זמין כלל

את השיבוץ עצמו בונים אחר כך מהמסך של המנהל.

הרצה מתוך קונטיינר ה-backend:
    cd /app/magen_merkava
    python build_team.py --team-password <סיסמה למנהל הצוות>

רק לראות מה ייבנה, בלי לשלוח:
    python build_team.py --dry-run --out profile.json
"""

from __future__ import annotations

import argparse
import datetime as dt
import http.cookiejar
import json
import os
import sys
import urllib.error
import urllib.request

from roster import ROSTER

TEAM_NAME = "אלחוט — מגן מרכבה"
DAY_START, NIGHT_START = "08:00", "20:00"
ALL_DAYS = ["יום ראשון", "יום שני", "יום שלישי", "יום רביעי", "יום חמישי", "יום שישי", "שבת"]

# לוח המשמרות: תא -> (אנשים במשמרת, אילו משמרות). בלי כחול.
CABS = {
    "א'": (3, ("יום", "לילה")),
    "ת'": (3, ("יום", "לילה")),
    "ד'": (2, ("יום", "לילה")),
    "ע'": (2, ("יום", "לילה")),
    "מ'": (3, ("יום", "לילה")),
    "ח'": (3, ("יום", "לילה")),
    "ר'": (3, ("יום", "לילה")),
    "מרחקים": (2, ("יום", "לילה")),
    "התרעה": (6, ("יום", "לילה")),
    "ס'": (3, ("לילה",)),
    "רוחב": (2, ("יום",)),
    "חפיפות": (3, ("יום",)),
}

SERVICE = {"מילואים": "reserve", 'הצ"ח': "hatzach", 'אע"צ': "civilian", "סדיר": "standard"}
COMPETENCE = {1: "high", 2: "medium", 3: "weak"}

ROLE = "אלחוט"                 # התפקיד של כולם
RESERVE_DAYS_PER_WEEK = 4      # מילואים: עד 4 ימים בשבוע
FOUR_DAYS = {"מילואים"}
CYCLE_ID = "sadir"             # סדיר, אע"צ והצ"ח: סבב 12/2
CYCLE = {"id": CYCLE_ID, "name": "12/2", "base_days": 12, "home_days": 2, "groups": ["א", "ב"]}


def shift_name(cab: str, part: str) -> str:
    return f"{cab} · {part}"


def build_shifts() -> list[dict]:
    shifts = []
    for cab, (headcount, parts) in CABS.items():
        for part in parts:
            day = part == "יום"
            shifts.append({
                "name": shift_name(cab, part),
                "start_time": DAY_START if day else NIGHT_START,
                "end_time": NIGHT_START if day else DAY_START,
                "days": ALL_DAYS,
                "headcount": headcount,
                "allowed_roles": [ROLE],
                "is_night": not day,
                "shift_type": "overlap" if cab == "חפיפות" else "regular",
                "purpose": "לילה ראשון בלבד — אחריו אנשי הסיבוב עוברים לתא הבא שלהם" if cab == "ס'" else "",
                "requires_shift_manager": False,
            })
    return shifts


def cab_shifts(cab: str | None) -> list[str]:
    if not cab or cab not in CABS:
        return []
    return [shift_name(cab, part) for part in CABS[cab][1]]


def competence(p: dict) -> str:
    known = [v for v in (p["competency"], p["level"]) if v]
    return COMPETENCE[max(known)] if known else ""


def build_employees(start: dt.date) -> list[dict]:
    """כולם בתפקיד אלחוט, כל אחד במשמרות של התא שלו.
    אילוץ אחד בלבד: מי שחסום, לא יכול להגיע או לא בפול — לא זמין כלל."""
    people, next_group = [], {}
    for p in ROSTER:
        person = {
            "name": p["name"],
            "role": ROLE,
            "eligible_shifts": cab_shifts(p["cab"]) + cab_shifts(p["then_cab"]),
            "service_type": SERVICE.get(p["service"], "standard"),
            "competence": competence(p),
            "notes": "",  # ריק — חוץ ממי שלא זמין
        }
        if p["service"] in FOUR_DAYS:
            person.update(service_type="reserve", exit_pattern="none",
                          reserve_days_per_week=RESERVE_DAYS_PER_WEEK)
        else:
            # סדיר, אע"צ והצ"ח בסבב 12/2: חצי מכל תא בקבוצה א' וחצי בקבוצה ב', כדי שלא כולם ייצאו יחד
            cab = p["then_cab"] or p["cab"]
            index = next_group.get(cab, 0)
            next_group[cab] = index + 1
            person.update(exit_pattern=f"cycle:{CYCLE_ID}", rotation_group=CYCLE["groups"][index % 2])
        if p["unavailable"]:  # האילוץ היחיד: חסום / לא יכול להגיע / לא בפול -> לא זמין כלל
            person["inactive_from"] = start.isoformat()
            person["notes"] = "לא זמין/ה: " + p["unavailable"]
        people.append(person)
    return people


def build_profile(start: dt.date) -> dict:
    return {
        "workplace": {"name": TEAM_NAME, "rotation_mode": "round", "planning_horizon": "שבוע",
                      "day_cycles": [dict(CYCLE, anchor_date=start.isoformat())]},
        "shifts": build_shifts(),
        "employees": build_employees(start),
        "rules": [],
        "summary": "צוות אלחוט בקריאת מגן מרכבה. שתי משמרות ביממה, 08:00-20:00 ו-20:00-08:00, כל תא לפי התקינה בלוח. "
                   "סדיר, אע\"צ והצ\"ח בסבב 12/2; מילואים עד 4 ימים בשבוע.",
    }


def send(profile: dict, url: str, admin_password: str, team_password: str, name: str) -> None:
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    base = url.rstrip("/")

    def call(method: str, path: str, body: dict) -> dict:
        request = urllib.request.Request(base + path, data=json.dumps(body).encode("utf-8"), method=method,
                                         headers={"Content-Type": "application/json"})
        try:
            with opener.open(request) as response:
                return json.loads(response.read() or b"{}")
        except urllib.error.HTTPError as error:
            sys.exit("%s %s נכשל (%d): %s" % (method, path, error.code, error.read().decode("utf-8", "replace")))
        except urllib.error.URLError as error:
            sys.exit(f"אין חיבור לשרת ב-{base}: {error.reason}")

    call("POST", "/api/admin/login", {"password": admin_password})
    team = call("POST", "/api/admin/teams", {"name": name, "password": team_password})
    call("POST", "/api/workspace/login", {"team_id": team["id"], "password": team_password})
    call("PUT", "/api/profile", profile)
    print(f"נפתח הצוות '{name}' ({team['id']}).")
    print("כניסה: בוחרים את הצוות במסך הכניסה ומזינים את סיסמת המנהל שבחרת.")


def report(profile: dict) -> None:
    people = profile["employees"]
    cycle = profile["workplace"]["day_cycles"][0]
    print(f"צוות: {profile['workplace']['name']}")
    print(f"משמרות: {len(profile['shifts'])}")
    for s in profile["shifts"]:
        print(f"  {s['name']:16} {s['start_time']}-{s['end_time']}  {s['headcount']} אנשים")
    sadir = [p for p in people if p["exit_pattern"].startswith("cycle:")]
    print(f"אנשים: {len(people)} — סדיר/אע\"צ/הצ\"ח בסבב {cycle['name']} (מ-{cycle['anchor_date']}): {len(sadir)}, "
          f"מילואים עד {RESERVE_DAYS_PER_WEEK} ימים בשבוע: {len(people) - len(sadir)}, "
          f"לא זמינים: {sum(1 for p in people if p.get('inactive_from'))}")
    for p in people:
        track = ("[לא זמין] " if p.get("inactive_from") else "") + (f"12/2 קבוצה {p['rotation_group']}" if p in sadir else f"עד {p['reserve_days_per_week']} ימים בשבוע")
        cab = p["eligible_shifts"][0].split(" · ")[0] if p["eligible_shifts"] else "-"
        print(f"  {cab:8} {p['name']:24} {p['competence'] or 'לא מדורג':7} {track}")


def main() -> int:
    ap = argparse.ArgumentParser(description="בניית צוות האלחוט — מגן מרכבה")
    ap.add_argument("--url", default="http://localhost:8000", help="כתובת ה-backend (מתוך הקונטיינר: localhost:8000)")
    ap.add_argument("--admin-password",
                    default=os.environ.get("PAKASH_ADMIN_PASSWORD") or os.environ.get("PAKASH_SETTINGS_PASSWORD") or "010802",
                    help="סיסמת קונסולת המפעיל (/admin)")
    ap.add_argument("--team-password", help="הסיסמה שתהיה למנהל הצוות החדש")
    ap.add_argument("--name", default=TEAM_NAME, help="שם הצוות")
    ap.add_argument("--start", type=dt.date.fromisoformat, default=dt.date.today(),
                    help="היום הראשון של סבב ה-12/2 (YYYY-MM-DD). ברירת מחדל: היום")
    ap.add_argument("--dry-run", action="store_true", help="רק להדפיס מה ייבנה, בלי לשלוח לשרת")
    ap.add_argument("--out", help="לשמור את הפרופיל לקובץ JSON")
    args = ap.parse_args()

    profile = build_profile(args.start)
    profile["workplace"]["name"] = args.name
    report(profile)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(profile, f, ensure_ascii=False, indent=2)
        print(f"\nנשמר: {args.out}")
    if args.dry_run:
        return 0
    if not args.team_password:
        sys.exit("חסר --team-password (הסיסמה של מנהל הצוות החדש)")
    print()
    send(profile, args.url, args.admin_password, args.team_password, args.name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
