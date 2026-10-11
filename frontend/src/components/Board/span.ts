import type { Schedule } from "@/types";

/** A stretch of dates, cut out of the periods that hold it.
 *
 *  The board draws three things a stored period is not: one day of a week,
 *  two weeks, a month. Each is the same rows with different bounds, so both
 *  functions here answer with an ordinary `Schedule` — which is what lets
 *  the index, the tiles and the filters read a day or a month exactly as
 *  they read a week, with no second code path that counts differently.
 *
 *  **What comes back is for reading only.** It carries no id and is always
 *  a draft in name: nothing here is a period a write could be aimed at, and
 *  an empty id is what makes sending one fail loudly instead of landing on
 *  whichever period happened to come first.
 */

/** The rows of one period falling inside `start`..`end`.
 *
 *  A finding with no date — a weekly total such as hours over the ceiling —
 *  is dropped: it describes the period, not any day in it, and the cells of
 *  the grid cannot show it either. It is still on the week it belongs to. */
export function clipTo(schedule: Schedule, start: string, end: string): Schedule {
  const inside = (date: string) => date >= start && date <= end;
  return {
    ...schedule,
    slots: schedule.slots.filter((row) => inside(row.slot_date)),
    assignments: schedule.assignments.filter((row) => inside(row.date)),
    warnings: schedule.warnings.filter((row) => inside(row.date)),
    closures: (schedule.closures ?? []).filter((row) => inside(row.date)),
  };
}

/** Several periods as one span, clipped to it. Null when there are none.
 *
 *  Periods never share a date, so concatenating their rows cannot place one
 *  person on a slot twice or count a seat from two sources. */
export function mergePeriods(
  periods: Schedule[],
  start: string,
  end: string,
): Schedule | null {
  if (!periods.length) return null;
  const clipped = periods.map((period) => clipTo(period, start, end));
  return {
    ...clipped[0],
    id: "",
    starts_on: start,
    ends_on: end,
    status: "draft",
    slots: clipped.flatMap((period) => period.slots),
    assignments: clipped.flatMap((period) => period.assignments),
    warnings: clipped.flatMap((period) => period.warnings),
    closures: clipped.flatMap((period) => period.closures),
    notes: [],
    summary: "",
  };
}

/** The stored period a date belongs to, if any of these holds it. */
export function periodOn(periods: Schedule[], date: string): Schedule | null {
  return (
    periods.find(
      (period) => period.starts_on <= date && period.ends_on >= date,
    ) ?? null
  );
}
