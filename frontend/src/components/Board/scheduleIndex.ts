"use client";

import type {
  Assignment,
  CardPerson,
  Schedule,
  ScheduleWarning,
  Slot,
} from "@/types";

import { touchKey as key } from "./agentTouch";

/** The week, bucketed by cell, built once instead of re-scanned per cell.
 *
 *  `BoardGrid` asks three questions of every cell it draws — which slot runs
 *  here, who is on it, what is wrong with it — and the straightforward way to
 *  answer each is a `.filter()` over the schedule. That is correct and it is
 *  what the grid did, but it makes drawing a week O(cells × rows): seven days
 *  by however many shifts, each walking the full assignment, slot and warning
 *  lists. The arithmetic is the same either way; doing it once per week rather
 *  than once per cell is the only difference.
 *
 *  Keyed `shift|date`, the same key the cells and `agentTouch` already use, so
 *  there is one spelling of "which cell" in the board rather than two.
 *
 *  **A missing bucket means an empty cell, never a missing schedule.** Every
 *  lookup returns an empty array rather than `undefined`, because a cell with
 *  nobody on it and a cell the index never heard of must render identically —
 *  the grid draws from the *slot* list, so a key with no assignments is the
 *  ordinary case for an unstaffed shift.
 */
export interface ScheduleIndex {
  /** The slot running on this cell, if the shift runs that day at all. */
  slot: (shift: string, date: string) => Slot | undefined;
  /** Everyone assigned to this cell, unfiltered. */
  assignments: (shift: string, date: string) => Assignment[];
  /** Warnings landing on this cell, including whole-day ones. */
  warnings: (shift: string, date: string) => ScheduleWarning[];
  /** How many people are assigned to this cell, ignoring any filter.
   *
   *  Separate from `assignments()` because the two are asked for different
   *  reasons: the cards are a *filtered view*, and headcount is what the cell
   *  is measured against. A cell filtered down to one person must not start
   *  claiming it is short of the other two. */
  assignedCount: (shift: string, date: string) => number;
  /** How many of this cell's seats are filled, ignoring any filter.
   *
   *  Not the same number as `assignedCount`: somebody shadowing the shift is
   *  standing on it and is not one of the people it asked for, so a cell can
   *  hold five cards and still be a seat short. This is the number the "חסרים"
   *  badge and the coverage rail are measured against, because it is the one
   *  `bl/audit.py` computes the unfilled warning from. */
  filledSeats: (shift: string, date: string) => number;
  /** Assigned and required across one day, for the column head. */
  dayCoverage: (date: string) => { assigned: number; required: number };
  /** The shift vocabulary in the order the slots declare it (D9).
   *
   *  Declaration order, not display order: `shiftOrder.ts` is what decides
   *  which row the board draws first, and it starts from this list. Keeping
   *  the raw order here means the two can disagree without either being
   *  wrong — this is what the schedule said, that is how it reads best. */
  shifts: string[];
}

const NO_ASSIGNMENTS: Assignment[] = [];
const NO_WARNINGS: ScheduleWarning[] = [];

export function buildScheduleIndex(
  schedule: Schedule | null,
  /** The roster, for the one fact the assignments do not carry: whether the
   *  person on a card fills a seat. Optional so a caller that has not loaded
   *  the roster yet still gets a usable index — everybody counts, which is
   *  what the board did before shadow shifts were counted at all. */
  people: Record<string, CardPerson> = {},
): ScheduleIndex {
  const slots = new Map<string, Slot>();
  const assignments = new Map<string, Assignment[]>();
  const seats = new Map<string, number>();
  const warnings = new Map<string, ScheduleWarning[]>();
  const byDay = new Map<string, { assigned: number; required: number }>();
  // The vocabulary in the order the slots name it, kept as-is. Never sorted
  // here: inventing an order is `shiftOrder.ts`'s job, and it needs this one
  // to fall back on for a shift the vocabulary gave no hours to (D9).
  const shiftOrder: string[] = [];
  const seenShifts = new Set<string>();

  const day = (date: string) => {
    let row = byDay.get(date);
    if (!row) {
      row = { assigned: 0, required: 0 };
      byDay.set(date, row);
    }
    return row;
  };

  for (const slot of schedule?.slots ?? []) {
    slots.set(key(slot.shift_name, slot.slot_date), slot);
    day(slot.slot_date).required += slot.headcount || 0;
    if (!seenShifts.has(slot.shift_name)) {
      seenShifts.add(slot.shift_name);
      shiftOrder.push(slot.shift_name);
    }
  }

  for (const row of schedule?.assignments ?? []) {
    const at = key(row.shift, row.date);
    push(assignments, at, row);
    if (people[row.employee]?.counts_toward_staffing !== false) {
      seats.set(at, (seats.get(at) ?? 0) + 1);
    }
  }

  // Filled seats against required seats, per day. Capped per cell, so a shift
  // somebody was doubled up on does not lend its spare body to the shift next
  // to it and report a short day as covered — the same cap
  // `simulate._coverage` applies, for the same reason.
  for (const [at, slot] of slots) {
    const filled = Math.min(seats.get(at) ?? 0, slot.headcount || 0);
    day(slot.slot_date).assigned += filled;
  }

  // A warning with an empty `shift` is about the whole day, so it is filed
  // against every shift running that day rather than looked up twice at read
  // time. `audit.py` emits both kinds and the grid must show either.
  for (const row of schedule?.warnings ?? []) {
    if (row.shift) {
      push(warnings, key(row.shift, row.date), row);
      continue;
    }
    for (const shift of shiftOrder) {
      if (slots.has(key(shift, row.date))) {
        push(warnings, key(shift, row.date), row);
      }
    }
  }

  return {
    slot: (shift, date) => slots.get(key(shift, date)),
    assignments: (shift, date) =>
      assignments.get(key(shift, date)) ?? NO_ASSIGNMENTS,
    warnings: (shift, date) => warnings.get(key(shift, date)) ?? NO_WARNINGS,
    assignedCount: (shift, date) =>
      (assignments.get(key(shift, date)) ?? NO_ASSIGNMENTS).length,
    filledSeats: (shift, date) => seats.get(key(shift, date)) ?? 0,
    dayCoverage: (date) => byDay.get(date) ?? { assigned: 0, required: 0 },
    shifts: shiftOrder,
  };
}

function push<T>(map: Map<string, T[]>, at: string, row: T): void {
  const existing = map.get(at);
  if (existing) existing.push(row);
  else map.set(at, [row]);
}
