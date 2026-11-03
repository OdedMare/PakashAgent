"""בונה את שיבוץ צוות האלחוט — מגן מרכבה.

שתי משמרות ביממה, 12 שעות כל אחת:
    בוקר 08:00-20:00
    לילה 20:00-08:00

כל תא מאויש מהאנשים שלו בלבד (לפי לוח המשמרות), לפי התקינה בתא.

הרצה:
    python3 build_team.py --start 2026-11-04 --days 7
    python3 build_team.py --start 2026-11-04 --days 7 --full-emergency   # כולל "רק בחירום מלא"
    python3 build_team.py ... --csv shibutz.csv

דורש: pip install "ortools>=9.12,<10"
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
from collections import defaultdict

from ortools.sat.python import cp_model

from roster import EXCLUDE_FLAGS, ROSTER, is_senior, needs_senior

DAY, NIGHT = "בוקר", "לילה"
SHIFT_HOURS = {DAY: "08:00-20:00", NIGHT: "20:00-08:00"}
SHIFT_OFFSET = {DAY: 0, NIGHT: 12}  # שעות מתחילת היממה (08:00)

# ---------------------------------------------------------------------------
# לוח המשמרות: תקינה בתא (כמה אנשים בכל משמרת) ואילו משמרות פעילות
#   days=None  -> כל יום
#   days={0}   -> רק ביום הראשון (0 = היום הראשון של הקריאה)
# משמרת "כחול" לא נכללת לפי בקשה.
# ---------------------------------------------------------------------------
CABS = {
    "א'":     dict(per_shift=3, shifts=(DAY, NIGHT), days=None),
    "ת'":     dict(per_shift=3, shifts=(DAY, NIGHT), days=None),
    "ד'":     dict(per_shift=2, shifts=(DAY, NIGHT), days=None),
    "ע'":     dict(per_shift=2, shifts=(DAY, NIGHT), days=None),
    "מ'":     dict(per_shift=3, shifts=(DAY, NIGHT), days=None),
    "ח'":     dict(per_shift=3, shifts=(DAY, NIGHT), days=None),
    "ר'":     dict(per_shift=3, shifts=(DAY, NIGHT), days=None),
    "מרחקים": dict(per_shift=2, shifts=(DAY, NIGHT), days=None),
    "התרעה":  dict(per_shift=6, shifts=(DAY, NIGHT), days=None),
    # משמרת אחת ביממה:
    "ס'":     dict(per_shift=3, shifts=(NIGHT,), days={0}),  # הסיבוב — לילה ראשון, ואז מתחלקים לתאים
    "רוחב":   dict(per_shift=2, shifts=(DAY,), days=None),
}
# חפיפות: משמרת אחת ביממה בלי תקינה — כל מי שבחפיפות מגיע לבוקר (לא דרך הפותר).
HANDOVER_CAB = "חפיפות"

# משקלות בפונקציית המטרה (גבוה = חשוב יותר)
W_HOLE = 1000          # משבצת לא מאוישת
W_NO_LEVEL1 = 40       # משמרת בתא בלי אף אחד ברמה 1
W_LOAD = 20            # העומס של האדם הכי עמוס בתא
W_SPREAD = 3          # פיזור שווה של משמרות בין אנשי התא
W_SWITCH = 5          # מעבר בוקר->לילה (עדיף שכל אחד יישאר באותו סוג משמרת)
W_UNCERTAIN = 4        # שיבוץ של מי שלא בטוח שיגיע / מגיע בתנאי
W_LEVEL3 = 2           # שיבוץ של רמה 3 / לא ידוע

HEB_DAYS = ["שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת", "ראשון"]


def cab_on_day(p: dict, d: int) -> str | None:
    """באיזה תא האדם יושב ביום d. אנשי הסיבוב: ס' ביום הראשון, אחר כך then_cab."""
    if p.get("then_cab"):
        return p["cab"] if d == 0 else p["then_cab"]
    return p["cab"]


def why_excluded(p: dict, full_emergency: bool) -> str | None:
    if p["cab"] is None:
        return "לא בלוח המשמרות"
    if p["cab"] == HANDOVER_CAB:
        return None
    hit = set(p["flags"]) & EXCLUDE_FLAGS
    if hit:
        return p["note"] or ", ".join(sorted(hit))
    if "emergency_only" in p["flags"] and not full_emergency:
        return "רק בחירום מלא (הרץ עם --full-emergency כדי לשבץ)"
    return None


def allowed(p: dict, d: int, s: str, start: dt.date) -> bool:
    """אילוצים אישיים: 72 שעות ראשונות, שישי-שבת, בלי לילות."""
    flags = set(p["flags"])
    start_hour = d * 24 + SHIFT_OFFSET[s]
    if "first_72h_only" in flags and start_hour + 12 > 72:
        return False
    if "fri_sat_only" in flags and (start + dt.timedelta(days=d)).weekday() not in (4, 5):
        return False
    if "no_nights" in flags and s == NIGHT:
        return False
    return True


def build(start: dt.date, days: int, full_emergency: bool, time_limit: float):
    people = [p for p in ROSTER if why_excluded(p, full_emergency) is None and p["cab"] != HANDOVER_CAB]
    excluded = [(p, why_excluded(p, full_emergency)) for p in ROSTER if why_excluded(p, full_emergency)]

    m = cp_model.CpModel()
    x = {}  # (person_idx, day, shift) -> BoolVar
    for i, p in enumerate(people):
        for d in range(days):
            cab = cab_on_day(p, d)
            spec = CABS.get(cab)
            if not spec or (spec["days"] is not None and d not in spec["days"]):
                continue
            for s in spec["shifts"]:
                if allowed(p, d, s, start):
                    x[i, d, s] = m.new_bool_var(f"x{i}_{d}_{s}")

    obj = []
    holes = {}
    slots = []  # (day, shift, cab, demand, [person_idx])
    for d in range(days):
        for cab, spec in CABS.items():
            if spec["days"] is not None and d not in spec["days"]:
                continue
            for s in spec["shifts"]:
                who = [i for i, p in enumerate(people) if (i, d, s) in x and cab_on_day(p, d) == cab]
                demand = spec["per_shift"]
                hole = m.new_int_var(0, demand, f"hole_{d}_{s}_{cab}")
                m.add(sum(x[i, d, s] for i in who) + hole == demand)
                holes[d, s, cab] = hole
                obj.append(W_HOLE * hole)
                slots.append((d, s, cab, demand, who))

                # מי שלא מוסמך / לא מוכר — רק כשיש בכיר באותה משמרת ובאותו תא
                seniors = [i for i in who if is_senior(people[i])]
                for i in who:
                    if needs_senior(people[i]):
                        m.add(x[i, d, s] <= sum(x[j, d, s] for j in seniors))

                # עדיף לפחות אחד ברמה 1 בכל משמרת
                lvl1 = [i for i in who if people[i]["level"] == 1 and is_senior(people[i])]
                no_l1 = m.new_bool_var(f"nol1_{d}_{s}_{cab}")
                m.add(sum(x[i, d, s] for i in lvl1) + no_l1 >= 1)
                obj.append(W_NO_LEVEL1 * no_l1)

    # מנוחה: לא שתי משמרות ברצף (בוקר+לילה באותו יום, או לילה ואז בוקר למחרת)
    for i in range(len(people)):
        for d in range(days):
            a, b = x.get((i, d, DAY)), x.get((i, d, NIGHT))
            if a is not None and b is not None:
                m.add(a + b <= 1)
            c = x.get((i, d + 1, DAY))
            if b is not None and c is not None:
                m.add(b + c <= 1)
            # מעבר מבוקר ללילה למחרת — מותר (24 שעות מנוחה) אבל עדיף להימנע
            n = x.get((i, d + 1, NIGHT))
            if a is not None and n is not None:
                sw = m.new_bool_var(f"sw{i}_{d}")
                m.add(a + n - 1 <= sw)
                obj.append(W_SWITCH * sw)

    # חלוקת עומס הוגנת בתוך כל תא
    load = {i: sum(v for (j, _, _), v in x.items() if j == i) for i in range(len(people))}
    by_cab = defaultdict(list)
    for i, p in enumerate(people):
        by_cab[p.get("then_cab") or p["cab"]].append(i)
    for cab, idxs in by_cab.items():
        mx = m.new_int_var(0, 2 * days, f"max_{cab}")
        for i in idxs:
            m.add(load[i] <= mx)
        obj.append(W_LOAD * mx)
    # פיזור: ריבוע העומס — עדיף 6+6 על פני 7+5
    for i in range(len(people)):
        lv = m.new_int_var(0, 2 * days, f"load{i}")
        m.add(lv == load[i])
        sq = m.new_int_var(0, 4 * days * days, f"sq{i}")
        m.add_multiplication_equality(sq, [lv, lv])
        obj.append(W_SPREAD * sq)

    for i, p in enumerate(people):
        flags = set(p["flags"])
        w = (W_UNCERTAIN if flags & {"uncertain", "conditional"} else 0) + (W_LEVEL3 if needs_senior(p) else 0)
        if w:
            obj.append(w * load[i])

    m.minimize(sum(obj))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.num_workers = 8
    status = solver.solve(m)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise SystemExit("לא נמצא שיבוץ — בדוק את האילוצים")

    schedule = []  # (day, shift, cab, [names], hole)
    for d, s, cab, demand, who in slots:
        names = [people[i] for i in who if solver.value(x[i, d, s])]
        schedule.append((d, s, cab, names, solver.value(holes[d, s, cab])))
    loads = {people[i]["name"]: solver.value(load[i]) for i in range(len(people))}
    handover = [p for p in ROSTER if p["cab"] == HANDOVER_CAB and not set(p["flags"]) & EXCLUDE_FLAGS]
    return schedule, loads, people, excluded, handover, solver.status_name(status)


def mark(p: dict) -> str:
    f = set(p["flags"])
    tags = []
    if needs_senior(p):
        tags.append("צריך בכיר")
    if "uncertain" in f:
        tags.append("לא בטוח שיגיע")
    if "conditional" in f:
        tags.append("בתנאי")
    if "first_72h_only" in f:
        tags.append("72 ש'")
    if "sensitive" in f:
        tags.append("לתשומת לב")
    if "rear_cab_only" in f:
        tags.append("תא אחורי בלבד")
    return p["name"] + (f" ({', '.join(tags)})" if tags else "")


def main():
    ap = argparse.ArgumentParser(description="שיבוץ צוות אלחוט — מגן מרכבה")
    ap.add_argument("--start", type=dt.date.fromisoformat, default=dt.date.today() + dt.timedelta(days=1),
                    help="תאריך היום הראשון (המשמרת הראשונה מתחילה בו ב-08:00)")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--full-emergency", action="store_true", help='לשבץ גם את מי שמגיע "רק בחירום מלא"')
    ap.add_argument("--csv", help="לשמור את השיבוץ לקובץ CSV (נפתח באקסל)")
    ap.add_argument("--time-limit", type=float, default=30.0)
    args = ap.parse_args()

    schedule, loads, people, excluded, handover, status = build(
        args.start, args.days, args.full_emergency, args.time_limit)

    print(f"שיבוץ צוות אלחוט — מגן מרכבה | {args.start} | {args.days} ימים | פותר: {status}\n")
    rows = []
    total_holes = 0
    for d in range(args.days):
        date = args.start + dt.timedelta(days=d)
        print(f"=== יום {HEB_DAYS[date.weekday()]} {date:%d/%m} ===")
        for s in (DAY, NIGHT):
            print(f"  -- {s} {SHIFT_HOURS[s]} --")
            for dd, ss, cab, names, hole in schedule:
                if dd != d or ss != s:
                    continue
                total_holes += hole
                line = ", ".join(mark(p) for p in names) or "—"
                if hole:
                    line += f"   << חסרים {hole}"
                print(f"    {cab:8} {line}")
                for p in names:
                    rows.append([f"{date:%d/%m/%Y}", HEB_DAYS[date.weekday()], s, SHIFT_HOURS[s], cab, p["name"], p["note"]])
                for _ in range(hole):
                    rows.append([f"{date:%d/%m/%Y}", HEB_DAYS[date.weekday()], s, SHIFT_HOURS[s], cab, "<< חסר >>", ""])
            if s == DAY and handover:
                print(f"    {HANDOVER_CAB:8} {', '.join(p['name'] for p in handover)}")
                for p in handover:
                    rows.append([f"{date:%d/%m/%Y}", HEB_DAYS[date.weekday()], s, SHIFT_HOURS[s], HANDOVER_CAB, p["name"], p["note"]])
        print()

    print(f"סה\"כ משבצות חסרות: {total_holes}")
    holes_by_cab = defaultdict(int)
    for _, _, cab, _, hole in schedule:
        holes_by_cab[cab] += hole
    for cab, h in holes_by_cab.items():
        if h:
            print(f"  {cab}: חסרים {h}")

    print("\nעומס לאדם (מספר משמרות):")
    for cab in CABS:
        members = [p for p in people if (p.get("then_cab") or p["cab"]) == cab]
        if members:
            print(f"  {cab}: " + ", ".join(f"{p['name']} {loads[p['name']]}" for p in members))

    print("\nלא משובצים:")
    for p, why in excluded:
        print(f"  {p['cab'] or '-':8} {p['name']} — {why}")

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["תאריך", "יום", "משמרת", "שעות", "תא", "שם", "הערה"])
            w.writerows(rows)
        print(f"\nנשמר: {args.csv}")


if __name__ == "__main__":
    main()
