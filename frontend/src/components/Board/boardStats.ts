import type { CardPerson, Schedule, ShiftStats } from "@/types";

/** Whether this period is the one to render for the displayed week.
 *
 *  Containment, not overlap, and the difference is a bug this used to have.
 *  `starts_on <= end && ends_on >= start` is true when a period touches the
 *  week by a single day, so paging off the end of a period kept the old
 *  period on screen — rendered *as* the new week, with no loading state,
 *  until `/at` answered. The server resolves a day by containment
 *  (`schedule_service.period_at`), and the two rules have to agree: a period
 *  the board would not get back from `/at` for this week is not this week's
 *  schedule, whatever it overlaps.
 *
 *  Both bounds are checked because a week is a range. A period covering only
 *  part of the week is not a stand-in for it either — the missing days would
 *  render as empty columns rather than as the unread days they are. */
export function covers(schedule: Schedule, start: string, end: string): boolean {
  return schedule.starts_on <= start && schedule.ends_on >= end;
}

/** The tiles for a period the overview did not compute.
 *
 *  Counted off the schedule's own slots and assignments — the same two lists
 *  `audit.py` counts — so a paged-to week reports itself rather than
 *  borrowing the current period's totals. Coverage and gaps only: hours need
 *  the profile's shift lengths and weights, and guessing those in the
 *  browser is exactly the second implementation the stats panel exists to
 *  avoid. The four tiles that would be fiction read zero rather than wrong. */
export function statsFor(
  schedule: Schedule,
  people: Record<string, CardPerson>,
): ShiftStats {
  const required = schedule.slots.reduce(
    (total, slot) => total + (slot.headcount || 0),
    0,
  );
  // Seats per cell, shadow shifts excluded — `audit._coverage`'s arithmetic,
  // since these tiles sit beside the ones that panel renders and two numbers
  // for one week is worse than one week with no numbers.
  const seats = new Map<string, number>();
  for (const row of schedule.assignments) {
    if (people[row.employee]?.counts_toward_staffing === false) continue;
    const at = `${row.shift}|${row.date}`;
    seats.set(at, (seats.get(at) ?? 0) + 1);
  }

  let assigned = 0;
  let unfilled = 0;
  for (const slot of schedule.slots) {
    const filled = seats.get(`${slot.shift_name}|${slot.slot_date}`) ?? 0;
    const needed = slot.headcount || 0;
    // Capped: three people on a one-person shift is one place covered and two
    // overstaffed, not three places filled. Uncapped, an overstaffed Sunday
    // paid for an unstaffed Monday and the week read as fully covered.
    assigned += Math.min(filled, needed);
    if (filled < needed) unfilled += 1;
  }

  return {
    ...EMPTY_STATS,
    total_shifts: schedule.assignments.length,
    people_working: new Set(schedule.assignments.map((row) => row.employee))
      .size,
    coverage: {
      required,
      assigned,
      unfilled_slots: unfilled,
      percent: required ? Math.round((assigned / required) * 100) : 100,
    },
  };
}

export const EMPTY_STATS: ShiftStats = {
  total_hours: 0,
  total_shifts: 0,
  total_nights: 0,
  people_working: 0,
  coverage: { required: 0, assigned: 0, unfilled_slots: 0, percent: 100 },
  by_shift: [],
  by_day: [],
  by_employee: [],
  warning_counts: [],
  conflicts: 0,
  constraint_pressure: { blocked: 0, people: 0, conflicts: 0, honored: 0 },
};
