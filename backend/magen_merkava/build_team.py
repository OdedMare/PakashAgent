"""בונה את צוות האלחוט — מגן מרכבה במערכת משמרות זהב.

הסקריפט לא משבץ משמרות. הוא פותח צוות במערכת ומגדיר בו:
  * את האנשים — תא, סוג שירות, כשירות, הערות, מי לא פעיל
  * את סוגי המשמרות — לכל תא בוקר 08:00-20:00 ולילה 20:00-08:00, עם התקינה מהלוח
  * את האילוצים — אילוצים קבועים לאנשים (בלי לילות, רק שישי-שבת) וכללים במילים

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

SERVICE = {"מילואים": "reserve", 'הצ"ח': "hatzach", 'אע"צ': "civilian", "חובה": "standard", "קבע": "standard"}
COMPETENCE = {1: "high", 2: "medium", 3: "weak"}

# מי לא פעיל במערכת (inactive_from = היום) — אפשר להחזיר אותו מהמסך
INACTIVE_FLAGS = {"blocked", "unavailable", "not_in_pool", "under_review", "refuser"}


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
                "allowed_roles": [cab],
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


def notes(p: dict) -> str:
    parts = [p["note"]] if p["note"] else []
    parts.append("כשירות: %s | רמה: %s" % (p["competency"] or "לא ידוע", p["level"] or "לא ידוע"))
    if p.get("then_cab"):
        parts.append(f"ס' בלילה הראשון, אחר כך {p['then_cab']}")
    if p["source"]:
        parts.append(f"מקור: {p['source']}")
    if p["sheet_assignment"] and p["sheet_assignment"] != p["cab"]:
        parts.append(f"בגיליון רשום: {p['sheet_assignment']}")
    if "rear_cab_only" in p["flags"]:
        parts.append("מוסמכת רק לתא אחורי")
    if "verify" in p["flags"]:
        parts.append("לבדוק שם/פרטים מול הגיליון")
    return " | ".join(parts)


def recurring(p: dict, eligible: list[str]) -> list[dict]:
    flags, rows = set(p["flags"]), []
    nights = [s for s in eligible if s.endswith("לילה")]
    if "no_nights" in flags and nights:
        rows.append({"days": ALL_DAYS, "shifts": nights, "available": False, "is_hard": True,
                     "reason": p["note"] or "בלי לילות"})
    if "fri_sat_only" in flags and eligible:
        rows.append({"days": ALL_DAYS[:5], "shifts": eligible, "available": False, "is_hard": True,
                     "reason": p["note"] or "רק שישי-שבת"})
    return rows


def build_employees(today: dt.date, start: dt.date | None, full_emergency: bool) -> list[dict]:
    people = []
    for p in ROSTER:
        if p["cab"] is None:
            continue  # לא בלוח המשמרות (דולב — מפקדת שמע)
        eligible = cab_shifts(p["cab"]) + cab_shifts(p.get("then_cab"))
        flags = set(p["flags"])
        person = {
            "name": p["name"],
            "role": p["cab"],
            "eligible_shifts": eligible,
            "service_type": SERVICE.get(p["service"], "standard"),
            "exit_pattern": "none",
            "competence": competence(p),
            "notes": notes(p),
            "recurring_constraints": recurring(p, eligible),
        }
        if p.get("then_cab"):
            person["qualifications"] = [{"role": "ס'", "last_active": ""}, {"role": p["then_cab"], "last_active": ""}]
        inactive = flags & INACTIVE_FLAGS or ("emergency_only" in flags and not full_emergency)
        if inactive:
            person["inactive_from"] = today.isoformat()
        elif "first_72h_only" in flags and start:
            person["inactive_from"] = (start + dt.timedelta(days=3)).isoformat()
        people.append(person)
    return people


def build_rules() -> list[dict]:
    rules = [
        {"text": "כל אחד עובד רק במשמרות של התא שלו.", "priority": "hard"},
        {"text": "אין שתי משמרות ברצף — לפחות 12 שעות מנוחה בין משמרות.", "priority": "hard"},
        {"text": "משמרת ס' · לילה פועלת רק בלילה הראשון של הקריאה. אחריו אנשי הסיבוב עוברים לתא הבא שלהם "
                 "(זוהר גולרוך ואלישי בטסאן ל-ד', אליצפן ריינהיאן ושר דלהים ל-ע', ספיר ניסני ל-מ', נעה כהן ל-א').",
         "priority": "hard"},
        {"text": "בכל משמרת בכל תא צריך לפחות אחד ברמה גבוהה.", "priority": "soft"},
        {"text": "כל אחד נשאר כמה שאפשר באותו סוג משמרת — יום או לילה.", "priority": "soft"},
        {"text": "חלוקה שווה של משמרות בין אנשי אותו תא.", "priority": "soft"},
    ]
    for p in ROSTER:
        flags, name = set(p["flags"]), p["name"]
        if p["cab"] is None or flags & INACTIVE_FLAGS:
            continue
        if flags & {"not_certified", "unknown_person"} or p["level"] == 3:
            rules.append({"text": f"{name} משובץ/ת רק כשבאותה משמרת יש איש צוות מנוסה (רמה 1-2) מהתא.",
                          "priority": "hard"})
        if "first_72h_only" in flags:
            rules.append({"text": f"{name} זמין/ה רק ב-72 השעות הראשונות של הקריאה.", "priority": "hard"})
        if "uncertain" in flags or "conditional" in flags:
            rules.append({"text": f"להעדיף לא לשבץ את {name} ({p['note']}).", "priority": "soft"})
    return rules


def build_profile(start: dt.date | None, full_emergency: bool) -> dict:
    today = dt.date.today()
    return {
        "workplace": {"name": TEAM_NAME, "rotation_mode": "round", "planning_horizon": "שבוע"},
        "shifts": build_shifts(),
        "employees": build_employees(today, start, full_emergency),
        "rules": build_rules(),
        "audit_policy": {"max_weekly_hours": 84, "max_consecutive_days": 14, "min_rest_hours": 12},
        "unit_policy": {"max_weak_per_shift": 1},
        "rest_policy": "משמרות של 12 שעות; לפחות 12 שעות מנוחה בין משמרות.",
        "summary": "צוות אלחוט בקריאת מגן מרכבה. שתי משמרות ביממה, 08:00-20:00 ו-20:00-08:00, כל תא לפי התקינה בלוח.",
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
    active = [p for p in people if "inactive_from" not in p or p["inactive_from"] > dt.date.today().isoformat()]
    print(f"צוות: {profile['workplace']['name']}")
    print(f"משמרות: {len(profile['shifts'])}")
    for s in profile["shifts"]:
        print(f"  {s['name']:16} {s['start_time']}-{s['end_time']}  {s['headcount']} אנשים")
    print(f"אנשים: {len(people)} (פעילים: {len(active)})")
    for p in people:
        status = "" if p in active else f"  [לא פעיל מ-{p['inactive_from']}]"
        print(f"  {p['role']:8} {p['name']:24} {p['competence'] or 'לא מדורג':7}{status}")
    print(f"כללים: {len(profile['rules'])}")
    for r in profile["rules"]:
        print(f"  ({'חובה' if r['priority'] == 'hard' else 'העדפה'}) {r['text']}")


def main() -> int:
    ap = argparse.ArgumentParser(description="בניית צוות האלחוט — מגן מרכבה")
    ap.add_argument("--url", default="http://localhost:8000", help="כתובת ה-backend (מתוך הקונטיינר: localhost:8000)")
    ap.add_argument("--admin-password",
                    default=os.environ.get("PAKASH_ADMIN_PASSWORD") or os.environ.get("PAKASH_SETTINGS_PASSWORD") or "010802",
                    help="סיסמת קונסולת המפעיל (/admin)")
    ap.add_argument("--team-password", help="הסיסמה שתהיה למנהל הצוות החדש")
    ap.add_argument("--name", default=TEAM_NAME, help="שם הצוות")
    ap.add_argument("--start", type=dt.date.fromisoformat,
                    help="תאריך תחילת הקריאה (YYYY-MM-DD) — קובע מתי נגמרות 72 השעות הראשונות")
    ap.add_argument("--full-emergency", action="store_true", help='להשאיר פעיל גם את מי שמגיע "רק בחירום מלא"')
    ap.add_argument("--dry-run", action="store_true", help="רק להדפיס מה ייבנה, בלי לשלוח לשרת")
    ap.add_argument("--out", help="לשמור את הפרופיל לקובץ JSON")
    args = ap.parse_args()

    profile = build_profile(args.start, args.full_emergency)
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
