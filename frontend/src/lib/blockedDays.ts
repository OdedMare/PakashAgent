/** A soldier's fixed blocked weekdays ("דוד לא יכול להגיע ברביעי").
 *
 *  Not a field of its own: a blocked weekday is an ordinary structured rule
 *  in the person's `recurring_constraints` — whole day, every shift, hard,
 *  unavailable — so the solver, the audit and the board read it the way they
 *  read a recurring constraint recorded any other way (the constraint form,
 *  the manager's chat). These two functions read and rewrite that list for
 *  the seven checkboxes in `SoldierFields`. */

export const WEEKDAY_NAMES = ["ראשון", "שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת"];

export const BLOCKED_DAY_REASON = "יום חסום קבוע";

type Rule = Record<string, unknown>;

/** A rule that blocks whole days: unavailable, hard, every shift, no hours. */
function blocksWholeDays(rule: unknown): rule is Rule {
  if (!rule || typeof rule !== "object" || Array.isArray(rule)) return false;
  const row = rule as Rule;
  return row.available === false
    && row.is_hard !== false
    && (row.constraint_type ?? "availability") === "availability"
    && (!Array.isArray(row.shifts) || row.shifts.length === 0)
    && !row.start_time && !row.end_time;
}

/** The days one whole-day rule covers; a rule naming no day covers all seven. */
function daysOf(rule: Rule): string[] {
  const days = Array.isArray(rule.days)
    ? rule.days.filter((day): day is string => typeof day === "string" && WEEKDAY_NAMES.includes(day))
    : [];
  return days.length ? days : WEEKDAY_NAMES;
}

/** The weekdays this person is blocked on, Sunday first. */
export function blockedDaysOf(recurring: unknown): string[] {
  const blocked = new Set((Array.isArray(recurring) ? recurring : []).filter(blocksWholeDays).flatMap(daysOf));
  return WEEKDAY_NAMES.filter((day) => blocked.has(day));
}

/** The person's `recurring_constraints` with exactly `days` blocked.
 *
 *  A day unticked leaves every whole-day rule that named it (a rule left
 *  with no day is dropped); a day newly ticked joins one rule of its own.
 *  Rules of any other kind — one shift, a time window, a wish, a duty, old
 *  free text — are returned untouched and in place. */
export function withBlockedDays(recurring: unknown, days: string[]): unknown[] {
  const wanted = new Set(days);
  const covered = new Set<string>();
  const next: unknown[] = [];
  for (const rule of Array.isArray(recurring) ? recurring : []) {
    if (!blocksWholeDays(rule)) {
      next.push(rule);
      continue;
    }
    const kept = daysOf(rule).filter((day) => wanted.has(day));
    kept.forEach((day) => covered.add(day));
    if (kept.length) next.push({ ...rule, days: kept });
  }
  const added = WEEKDAY_NAMES.filter((day) => wanted.has(day) && !covered.has(day));
  if (added.length) {
    next.push({ days: added, shifts: [], available: false, is_hard: true, reason: BLOCKED_DAY_REASON, source: "manager" });
  }
  return next;
}
