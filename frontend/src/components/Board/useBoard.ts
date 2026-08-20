"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { checkPlacement, scheduleAt } from "@/services/api";
import type { PlacementCheck, Schedule } from "@/types";

/** The board's own state: which week is on screen, and what is filtered out.
 *
 *  Deliberately *beside* `useManagement` rather than inside it. That hook
 *  owns the server's answer — the overview, its warnings, the change log —
 *  and everything here is a question about what the manager is currently
 *  looking at. Folding the two together would make changing a filter refetch
 *  the world, and moving to next week discard a proposal the agent was in
 *  the middle of making.
 *
 *  **Nothing in this file calls the model.** Week arithmetic is arithmetic,
 *  and `check()` goes to `bl/placement.py`, which contains no LLM call at
 *  all. The board is fully operable with the agent unavailable — the agent
 *  is what makes it *conversational*, not what makes it work.
 */

/** Filters, as the toolbar sets them. Empty means "everything", never
 *  "nothing" — a board that hid every shift because no filter was chosen is
 *  the failure mode this default exists to prevent. */
export interface BoardFilters {
  employee: string;
  role: string;
  shift: string;
  status: "all" | "draft" | "published";
  /** Show only cells carrying a warning. */
  conflictsOnly: boolean;
  /** Show only slots short of their headcount. */
  unassignedOnly: boolean;
}

export const EMPTY_FILTERS: BoardFilters = {
  employee: "",
  role: "",
  shift: "",
  status: "all",
  conflictsOnly: false,
  unassignedOnly: false,
};

export interface BoardState {
  /** The Sunday of the week on screen, ISO. */
  weekStart: string;
  /** Its Saturday. Sunday-based because the workweek here is Israeli —
   *  the source files run ראשון through שבת, and a Monday-based week would
   *  split every one of them across two boards. */
  weekEnd: string;
  /** Today in the *browser's* timezone, ISO. The manager's local day is the
   *  one they mean by "today", and computing it server-side would put a
   *  manager in Israel on the server's date. */
  today: string;
  /** Whether the week on screen is the one containing today. */
  isCurrentWeek: boolean;
  previousWeek: () => void;
  nextWeek: () => void;
  goToToday: () => void;
  goToWeekOf: (iso: string) => void;
  filters: BoardFilters;
  setFilters: (next: Partial<BoardFilters>) => void;
  clearFilters: () => void;
  filtersActive: boolean;
  /** The period covering the displayed week, when one is stored and it is
   *  not the period the overview already handed us. Null while none is. */
  weekSchedule: Schedule | null;
  weekBusy: boolean;
  /** Re-read the displayed week from the server. */
  reloadWeek: () => Promise<void>;
  /** Ask what a placement would cost. No model call. */
  check: (input: {
    employee: string;
    shift_name: string;
    slot_date: string;
    schedule_id?: string;
    moving_assignment_id?: string;
  }) => Promise<PlacementCheck | null>;
}

/** Where the board opens, and where it stays for the session.
 *
 *  Held in `sessionStorage` rather than component state so returning from
 *  the roster or the settings panel lands back on the week the manager was
 *  working on. Session-scoped and not `localStorage` on purpose: a week is
 *  a thing you are in the middle of today, and a manager opening the app
 *  tomorrow means *this* week, not the one they last had open. */
const WEEK_KEY = "pakash.board.week";

export function useBoard(scheduleId?: string): BoardState {
  const today = useMemo(() => localToday(), []);
  const [weekStart, setWeekStart] = useState<string>(() => {
    const remembered = readRememberedWeek();
    return remembered ?? sundayOf(today);
  });
  const [filters, setFiltersState] = useState<BoardFilters>(EMPTY_FILTERS);
  const [weekSchedule, setWeekSchedule] = useState<Schedule | null>(null);
  const [weekBusy, setWeekBusy] = useState(false);

  const weekEnd = useMemo(() => addDays(weekStart, 6), [weekStart]);

  // Remembered on every move rather than on unmount: a manager who closes
  // the tab from a different week still comes back to it, and an unmount
  // handler does not run on a hard close.
  const goToWeek = useCallback((iso: string) => {
    const sunday = sundayOf(iso);
    setWeekStart(sunday);
    try {
      window.sessionStorage.setItem(WEEK_KEY, sunday);
    } catch {
      // A browser refusing storage is not a reason to refuse navigation.
    }
  }, []);

  const previousWeek = useCallback(
    () => goToWeek(addDays(weekStart, -7)),
    [goToWeek, weekStart],
  );
  const nextWeek = useCallback(
    () => goToWeek(addDays(weekStart, 7)),
    [goToWeek, weekStart],
  );
  const goToToday = useCallback(() => goToWeek(today), [goToWeek, today]);

  /** Load the period covering the displayed week.
   *
   *  Only when it is not the one already on screen. The overview hands over
   *  the *current* period, so the common case — a manager on this week —
   *  costs no extra request, and paging away is what fetches. */
  const reloadWeek = useCallback(async () => {
    setWeekBusy(true);
    try {
      const found = await scheduleAt(weekStart).catch(() => null);
      setWeekSchedule(found);
    } finally {
      setWeekBusy(false);
    }
  }, [weekStart]);

  useEffect(() => {
    let cancelled = false;
    setWeekBusy(true);
    scheduleAt(weekStart)
      .catch(() => null)
      .then((found) => {
        if (cancelled) return;
        setWeekSchedule(found);
        setWeekBusy(false);
      });
    return () => {
      cancelled = true;
    };
    // `scheduleId` is a dependency because a write to the current period
    // changes what `/at` answers for the week containing it — without it, a
    // freshly generated week would render against the pre-write copy.
  }, [weekStart, scheduleId]);

  const setFilters = useCallback((next: Partial<BoardFilters>) => {
    setFiltersState((current) => ({ ...current, ...next }));
  }, []);

  const clearFilters = useCallback(() => setFiltersState(EMPTY_FILTERS), []);

  const filtersActive = useMemo(
    () =>
      filters.employee !== "" ||
      filters.role !== "" ||
      filters.shift !== "" ||
      filters.status !== "all" ||
      filters.conflictsOnly ||
      filters.unassignedOnly,
    [filters],
  );

  /** What a placement would cost. Deterministic, no model.
   *
   *  Returns null on failure rather than throwing: a check that could not be
   *  made must not stop the manager from acting. The write path is guarded
   *  independently by the server, and the audit under the board reports the
   *  same facts a moment later — so the worst case of a failed check is that
   *  the warning arrives after the click instead of before it, which is
   *  exactly where it arrived before this feature existed. */
  const check = useCallback(
    async (input: {
      employee: string;
      shift_name: string;
      slot_date: string;
      schedule_id?: string;
      moving_assignment_id?: string;
    }) => {
      try {
        return await checkPlacement(input);
      } catch {
        return null;
      }
    },
    [],
  );

  return {
    weekStart,
    weekEnd,
    today,
    isCurrentWeek: weekStart === sundayOf(today),
    previousWeek,
    nextWeek,
    goToToday,
    goToWeekOf: goToWeek,
    filters,
    setFilters,
    clearFilters,
    filtersActive,
    weekSchedule,
    weekBusy,
    reloadWeek,
    check,
  };
}

/** The week the manager last had open this session, if any.
 *
 *  Read once at mount. A stored value that is not a date is discarded rather
 *  than trusted — `sessionStorage` is writable by anything on the origin,
 *  and a malformed week would render a board of `Invalid Date`. */
function readRememberedWeek(): string | null {
  try {
    const stored = window.sessionStorage.getItem(WEEK_KEY);
    if (!stored) return null;
    return Number.isNaN(new Date(`${stored}T00:00:00`).getTime())
      ? null
      : stored;
  } catch {
    return null;
  }
}

/** Today, in the browser's own timezone, as `YYYY-MM-DD`.
 *
 *  Built from the local date parts rather than `toISOString()`, which
 *  converts to UTC first: at 01:00 in Israel that returns *yesterday*, which
 *  would open the board on the previous week for two hours every night. */
export function localToday(): string {
  return isoOf(new Date());
}

/** The Sunday on or before this date.
 *
 *  Sunday-based to match `week_bounds()` in the repository, which is itself
 *  Sunday-based because the real source files run ראשון through שבת. The two
 *  must agree: a board built on a Monday week would ask the server for a
 *  period whose bounds never line up with what it renders. */
export function sundayOf(iso: string): string {
  const date = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(date.getTime())) return iso;
  date.setDate(date.getDate() - date.getDay());
  return isoOf(date);
}

export function addDays(iso: string, days: number): string {
  const date = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(date.getTime())) return iso;
  date.setDate(date.getDate() + days);
  return isoOf(date);
}

/** The seven dates of the week starting here, in order. */
export function weekDates(start: string): string[] {
  return Array.from({ length: 7 }, (_, index) => addDays(start, index));
}

function isoOf(date: Date): string {
  const month = `${date.getMonth() + 1}`.padStart(2, "0");
  const day = `${date.getDate()}`.padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
}
