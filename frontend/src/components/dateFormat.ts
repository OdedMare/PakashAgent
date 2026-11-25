import type { ConstraintRequestRow } from "@/types";

/** Date display formats, kept apart from `DateInput` so hooks and pure
 * modules can format a date without importing a component (and its icons). */

/** `DD/MM/YYYY`, the Israeli order, from an ISO `YYYY-MM-DD`. */
export function displayDate(iso: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  return match ? `${match[3]}/${match[2]}/${match[1]}` : iso;
}

/** `DD/MM`, for places where the year is already obvious from context. */
export function shortDate(iso: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  return match ? `${match[3]}/${match[2]}` : iso;
}

export function adjacentDateLabel(iso: string, offset: number): string {
  if (!iso) return "";
  const day = new Date(iso + "T00:00:00Z");
  day.setUTCDate(day.getUTCDate() + offset);
  return displayDate(day.toISOString().slice(0, 10));
}

export function requestPeriodLabel(row: ConstraintRequestRow) {
  const end = row.end_date || row.constraint_date;
  const period = displayDate(row.constraint_date) +
    (end === row.constraint_date ? "" : ` עד ${displayDate(end)}`);
  const parts = [period, row.shift_name || "כל היום"];
  if (row.before_shift) parts.push(`${adjacentDateLabel(row.constraint_date, -1)}: ${row.before_shift}`);
  if (row.after_shift) parts.push(`${adjacentDateLabel(end, 1)}: ${row.after_shift}`);
  return parts.join(" · ");
}
