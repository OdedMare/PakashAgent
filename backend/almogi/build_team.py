"""בונה את צוות אלמוגי במערכת משמרות זהב.

הסקריפט לא משבץ משמרות. הוא פותח צוות במערכת ומגדיר בו:
  * את האנשים: תפקיד, מבנה יציאות, קבוצה, מעמד והסמכה לחפיפה
  * את סוגי המשמרות: בוקר, ערב, לילה וכונן, אדם אחד בכל משמרת
  * את היציאות: 11/3, 10/4 וסגירה 1 ל־3 לקצינים
  * את הכללים הקבועים ואת גבולות העומס והמנוחה

את השיבוץ עצמו בונים אחר כך מהמסך של המנהל.

הרצה מתוך קונטיינר ה-backend:
    cd /app/almogi
    python build_team.py --team-password <סיסמה למנהל הצוות>

רק לראות מה ייבנה, בלי לשלוח:
    python build_team.py --dry-run --out profile.json
"""

from __future__ import annotations

import argparse
import http.cookiejar
import json
import os
import sys
import urllib.error
import urllib.request

from roster import ROSTER

TEAM_NAME = "אלמוגי"
ALL_DAYS = ["יום ראשון", "יום שני", "יום שלישי", "יום רביעי", "יום חמישי", "יום שישי", "שבת"]

# שם -> (התחלה, סיום, משקל עומס). None = ברירת המחדל של המערכת.
SHIFTS = {
    "בוקר": ("09:00", "17:00", None),
    "ערב": ("17:00", "01:00", None),
    "לילה": ("01:00", "09:00", None),
    "כונן": ("08:00", "01:00", 0.5),
}

# העוגן של 11/3 ו-10/4: היום שבו קבוצה א' נכנסת לבסיס.
# העוגן של 1 ל־3: השבוע שבו קבוצה א' סוגרת.
#
# שעות היציאה והחזרה (leave_day/return_day מזיזים את היום הנומינלי):
#   10/4   יוצאים בחמישי, חוזרים בשני 09:00. בלי ההזזה המחזור היה יוצא ברביעי
#          וחוזר בראשון.
#   11/3   יוצאים בחמישי, חוזרים בראשון 09:00.
#   1 ל־3  מי שלא סוגר יוצא בחמישי וחוזר בראשון 09:00.
SUNDAY_MORNING = "09:00"
CYCLES = {
    "11/3": {"id": "c113", "name": "11/3", "kind": "days", "base_days": 11, "home_days": 3,
             "groups": ["א", "ב"], "anchor_date": "2026-11-15",
             "return_time": SUNDAY_MORNING},
    "10/4": {"id": "c104", "name": "10/4", "kind": "days", "base_days": 10, "home_days": 4,
             "groups": ["א", "ב"], "anchor_date": "2026-11-15",
             "leave_day": 1, "return_day": 1, "return_time": SUNDAY_MORNING},
    "1 ל־3": {"id": "c13", "name": "1 ל־3", "kind": "weekends",
              "groups": ["א", "ב", "ג"], "anchor_date": "2026-11-19",
              "return_time": SUNDAY_MORNING},
}

RULES = [
    "אין לשבץ בוקר אחרי לילה",
    "אין לשבץ ערב אחרי לילה",
    "אין לשבץ כונן אחרי לילה",
    "אין לשבץ 3 ערבים רצוף",
    "אין לשבץ לילה לפני יציאה הביתה",
    "אין לשבץ קצינים ליותר מ-6 משמרות בחודש",
    "אין לשבץ משמרת בזמן אי-זמינות שחייל או קצין מגישים",
    "אין לשבץ בוקר בבוקר שבו עולים לבסיס",
    "אין לשבץ לילה מיד אחרי ערב",
    "אין לשבץ שני לילות רצוף",
]

LIMITS = {"max_weekly_hours": 3000, "max_consecutive_days": 11, "min_rest_hours": 8}

# העדפה, לא איסור: קצין/ה יקבל/תקבל לילה רק כשאין מי שיכסה אותו.
OFFICER_NIGHTS = {"days": ALL_DAYS, "shifts": ["לילה"], "available": False, "is_hard": False,
                  "reason": "קצין/ה: עדיף לא בלילה"}


def build_shifts() -> list[dict]:
    shifts = []
    for name, (start, end, weight) in SHIFTS.items():
        shift = {"name": name, "start_time": start, "end_time": end, "days": ALL_DAYS, "headcount": 1,
                 "shift_type": "regular", "requires_shift_manager": False}
        if weight is not None:
            shift["load_weight"] = weight
        shifts.append(shift)
    return shifts


def build_employees() -> list[dict]:
    people = []
    for p in ROSTER:
        officer, overlap = p["status"] == "קצין", p["status"] == "נחפף"
        people.append({
            "name": p["name"],
            "role": p["role"],
            "exit_pattern": "cycle:" + CYCLES[p["cycle"]]["id"],
            "rotation_group": p["group"],
            "service_type": "overlap" if overlap else "standard",
            "rank_group": "officer" if officer else "",
            "counts_toward_staffing": not overlap,
            "can_train": p["can_train"],
            "is_shift_manager": False,
            "eligible_shifts": list(SHIFTS),
            "recurring_constraints": [OFFICER_NIGHTS] if officer else [],
        })
    return people


def build_profile(name: str) -> dict:
    return {
        "workplace": {"name": name, "rotation_mode": "round", "planning_horizon": "שבוע",
                      "operating_days": ["ראשון", "שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת"],
                      "notes_visual_only": True,
                      "day_cycles": list(CYCLES.values())},
        "shifts": build_shifts(),
        "employees": build_employees(),
        "rules": [{"text": text, "priority": "hard"} for text in RULES],
        "audit_policy": LIMITS,
        "summary": "יחידה צבאית עם מבנה יציאות אישי לכל חייל/ת",
    }


def send(profile: dict, url: str, admin_password: str, team_password: str, name: str) -> None:
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    base = url.rstrip("/")

    def call(method: str, path: str, body: dict | None = None) -> dict | list:
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(base + path, data=data, method=method,
                                         headers={"Content-Type": "application/json"})
        try:
            with opener.open(request) as response:
                return json.loads(response.read() or b"{}")
        except urllib.error.HTTPError as error:
            sys.exit("%s %s נכשל (%d): %s" % (method, path, error.code, error.read().decode("utf-8", "replace")))
        except urllib.error.URLError as error:
            sys.exit(f"אין חיבור לשרת ב-{base}: {error.reason}")

    call("POST", "/api/admin/login", {"password": admin_password})
    if any(team.get("name") == name for team in call("GET", "/api/admin/teams")):
        sys.exit(f"כבר קיים צוות בשם '{name}'. לא נפתח צוות נוסף; אפשר לבחור שם אחר עם --name.")
    team = call("POST", "/api/admin/teams", {"name": name, "password": team_password})
    call("POST", "/api/workspace/login", {"team_id": team["id"], "password": team_password})
    call("PUT", "/api/profile", profile)
    print(f"נפתח הצוות '{name}' ({team['id']}).")
    print("כניסה: בוחרים את הצוות במסך הכניסה ומזינים את סיסמת המנהל שבחרת.")


def report(profile: dict) -> None:
    print(f"צוות: {profile['workplace']['name']}")
    print(f"משמרות: {len(profile['shifts'])}")
    for s in profile["shifts"]:
        print(f"  {s['name']:6} {s['start_time']}-{s['end_time']}  {s['headcount']} אנשים")
    print("יציאות:")
    for cycle in profile["workplace"]["day_cycles"]:
        print(f"  {cycle['name']:6} קבוצות {' / '.join(cycle['groups'])}, עוגן {cycle['anchor_date']}")
    print(f"אנשים: {len(ROSTER)}")
    for p in ROSTER:
        print(f"  {p['name']:10} {p['role']:5} {p['status']:5} {p['cycle']} קבוצה {p['group']}"
              + (" · מוסמך/ת לחפוף" if p["can_train"] else ""))
    print(f"כללים קבועים: {len(profile['rules'])}")
    for rule in profile["rules"]:
        print(f"  {rule['text']}")


def main() -> int:
    ap = argparse.ArgumentParser(description="בניית צוות אלמוגי")
    ap.add_argument("--url", default="http://localhost:8000", help="כתובת ה-backend (מתוך הקונטיינר: localhost:8000)")
    ap.add_argument("--admin-password",
                    default=os.environ.get("PAKASH_ADMIN_PASSWORD") or os.environ.get("PAKASH_SETTINGS_PASSWORD") or "010802",
                    help="סיסמת קונסולת המפעיל (/admin)")
    ap.add_argument("--team-password", help="הסיסמה שתהיה למנהל הצוות החדש")
    ap.add_argument("--name", default=TEAM_NAME, help="שם הצוות")
    ap.add_argument("--dry-run", action="store_true", help="רק להדפיס מה ייבנה, בלי לשלוח לשרת")
    ap.add_argument("--out", help="לשמור את הפרופיל לקובץ JSON")
    args = ap.parse_args()

    profile = build_profile(args.name)
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
