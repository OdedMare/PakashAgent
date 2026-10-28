/** A shift's weekend standard, read from and written into its `staffing`.
 *
 *  The profile already holds staffing per group of days — a group naming no
 *  days is the default, one naming a weekday wins over it on that day
 *  (`scheduler._staffing_requirements`, `audit.required_headcount`). A
 *  different weekend headcount is therefore one more group, naming שישי and
 *  שבת, and nothing downstream needs to know the form exists. */

export const WEEKEND_DAYS = ["שישי", "שבת"];

type Group = Record<string, unknown>;

/** The weekend headcount, or null when the weekend uses the default. */
export function weekendHeadcount(shift?: Record<string, unknown>): number | null {
  for (const group of groups(shift?.staffing)) {
    const days = dayList(group.days);
    if (!days.some(isWeekend)) continue;
    if (typeof group.headcount === "number") return group.headcount;
  }
  return null;
}

/** `staffing` with the weekend set to `headcount`, or back to the default.
 *
 *  Weekend days are taken out of every other day group first, so a Friday
 *  the interview recorded beside Thursday cannot outrank the number the
 *  manager just typed. Groups for the other weekdays are kept untouched. */
export function withWeekendHeadcount(staffing: unknown, headcount: number | null): Group[] {
  const rows = groups(staffing);
  const previous = rows.find((group) => dayList(group.days).some(isWeekend));
  const kept: Group[] = [];
  for (const group of rows) {
    const days = dayList(group.days);
    if (days.length === 0) {
      kept.push(group);
      continue;
    }
    const remaining = days.filter((day) => !isWeekend(day));
    if (remaining.length) kept.push({ ...group, days: remaining });
  }
  if (headcount === null) return kept;
  return [
    ...kept,
    {
      days: WEEKEND_DAYS,
      headcount,
      required_roles: Array.isArray(previous?.required_roles) ? previous.required_roles : [],
    },
  ];
}

function isWeekend(day: string): boolean {
  const key = day.startsWith("יום ") ? day.slice(4).trim() : day;
  return WEEKEND_DAYS.includes(key);
}

function groups(value: unknown): Group[] {
  return Array.isArray(value)
    ? value.filter((item): item is Group => Boolean(item) && typeof item === "object" && !Array.isArray(item))
    : [];
}

function dayList(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string").map((item) => item.trim()).filter(Boolean)
    : [];
}
