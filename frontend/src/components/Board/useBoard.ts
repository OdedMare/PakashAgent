"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { checkPlacement, scheduleAt, schedulesBetween } from "@/services/api";
import type { PlacementCheck, Schedule } from "@/types";

import { addDays, isDay, localToday, sundayOf } from "./dates";
import type { BoardView } from "./views";
import {
  isBoardView,
  isOverview,
  rangeOf,
  showsToday,
  stepFocus,
} from "./views";

export { addDays, weekDates } from "./dates";

/** The board's own state: which dates are on screen, and what is filtered out.
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
  /** Show only cells carrying a warning. */
  conflictsOnly: boolean;
  /** Show only slots short of their headcount. */
  unassignedOnly: boolean;
}

const EMPTY_FILTERS: BoardFilters = {
  employee: "",
  role: "",
  shift: "",
  conflictsOnly: false,
  unassignedOnly: false,
};

interface BoardState {
  /** How much of the calendar is on screen: a day, a week, two, or a month. */
  view: BoardView;
  setView: (view: BoardView) => void;
  /** The day the view is anchored on, ISO. The day view shows exactly this
   *  date; every wider view shows the whole weeks around it. */
  focus: string;
  /** The first and last date the view draws. */
  rangeStart: string;
  rangeEnd: string;
  /** The Sunday of the week the anchor is in, ISO.
   *
   *  Present in every view, because it is what names *the period in play*:
   *  the day and week views render it, and under a two-week or month view it
   *  is still the week the agent's conversation is about. */
  weekStart: string;
  /** Its Saturday. Sunday-based because the workweek here is Israeli —
   *  the source files run ראשון through שבת, and a Monday-based week would
   *  split every one of them across two boards. */
  weekEnd: string;
  /** Today in the *browser's* timezone, ISO. The manager's local day is the
   *  one they mean by "today", and computing it server-side would put a
   *  manager in Israel on the server's date. */
  today: string;
  /** Whether the span on screen is the one containing today. */
  isCurrent: boolean;
  /** One view-width back or forward: a day, a week, two weeks, a month. */
  previous: () => void;
  next: () => void;
  goToToday: () => void;
  goToWeekOf: (iso: string) => void;
  /** Open one date as a day, or the week around it — what a click in the
   *  two-week and month views does. */
  openDay: (iso: string) => void;
  openWeek: (iso: string) => void;
  filters: BoardFilters;
  setFilters: (next: Partial<BoardFilters>) => void;
  clearFilters: () => void;
  filtersActive: boolean;
  /** The period covering the displayed week, when one is stored and it is
   *  not the period the overview already handed us. Null while none is. */
  weekSchedule: Schedule | null;
  weekBusy: boolean;
  /** Why the displayed week could not be read, when it could not be.
   *
   *  Separate from `weekSchedule: null`, which means the server answered and
   *  there is genuinely no period stored here. Collapsing the two is what
   *  made a failed request render as "no schedule for this week" — an empty
   *  state with two build buttons on it, offered because the network was
   *  down. */
  weekError: string | null;
  /** Re-read the displayed week from the server. */
  reloadWeek: () => Promise<void>;
  /** Every period touching the span on screen, for the two views that cross
   *  periods. Empty under the day and week views, which never ask. */
  rangeSchedules: Schedule[];
  rangeBusy: boolean;
  /** Why the span could not be read. As with `weekError`, kept apart from an
   *  empty list, which means the server answered and nothing is stored. */
  rangeError: string | null;
  reloadRange: () => Promise<void>;
  refresh: (date?: string) => Promise<void>;
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

/** Which view the board opens in.
 *
 *  `localStorage`, unlike the date beside it, and for the reason the shift-row
 *  order is: *which week* is something you are in the middle of today, but
 *  *how wide you like to look* is a habit, and it holds tomorrow too. */
const VIEW_KEY = "pakash.board.view";

/** The week on hand: which one it is for, what it holds, and why it is empty
 *  if it is. `for` trailing `weekStart` is what "still loading" means. */
interface WeekState {
  for: string | null;
  schedule: Schedule | null;
  error: string | null;
}

/** One completed read, tagged with the request that made it, so the caller
 *  can drop it if a newer read has since started. */
interface WeekRead {
  token: number;
  week: WeekState;
}

/** The same two shapes for a span of periods. `for` is the span's own
 *  `start|end`, so paging and re-reading are told apart the same way. */
interface SpanState {
  for: string | null;
  schedules: Schedule[];
  error: string | null;
}

interface SpanRead {
  token: number;
  span: SpanState;
}

/** One array for "no periods", so a view that never asked does not hand its
 *  readers a fresh list — and a fresh memo — on every render. */
const NO_SCHEDULES: Schedule[] = [];

export function useBoard(scheduleId?: string, refreshKey?: number): BoardState {
  const today = useMemo(() => localToday(), []);
  const [focus, setFocus] = useState<string>(
    () => readRememberedDay() ?? today,
  );
  const [view, setViewState] = useState<BoardView>(readRememberedView);
  const [filters, setFiltersState] = useState<BoardFilters>(EMPTY_FILTERS);
  // The fetched week and whether a fetch is outstanding, as one value. Held
  // together rather than as two `useState`s because they change together and
  // always in the same direction: setting them separately inside an effect
  // is what produces the cascading render the compiler warns about, and
  // splitting them also allows a moment where a stale schedule is shown as
  // settled.
  const [week, setWeek] = useState<WeekState>({
    for: null,
    schedule: null,
    error: null,
  });

  // Every read of a week is answered against the request that is still the
  // newest, by the same token the board already uses for placement checks.
  //
  // The effect's own cleanup is not enough on its own. It cancels the read
  // whose deps changed, but `reloadWeek` is called from outside React — from
  // a write settling, from the refresh button — and has no cleanup to hang a
  // flag on. A reload begun on the 26th and landing after the manager has
  // moved to the 27th would otherwise write `{ for: "26th" }` over a
  // finished answer for the 27th, putting the board back into its loading
  // state for a week it had already read.
  const weekToken = useRef(0);
  const [span, setSpan] = useState<SpanState>({
    for: null,
    schedules: NO_SCHEDULES,
    error: null,
  });
  const spanToken = useRef(0);

  const weekStart = useMemo(() => sundayOf(focus), [focus]);
  const weekEnd = useMemo(() => addDays(weekStart, 6), [weekStart]);
  const range = useMemo(() => rangeOf(view, focus), [view, focus]);
  // What the span read is *for*. Null under the day and week views: they
  // are one period, which the week read below already has, and asking for
  // the span as well would audit the same period twice per render of it.
  const spanKey = isOverview(view) ? `${range.start}|${range.end}` : null;

  // Remembered on every move rather than on unmount: a manager who closes
  // the tab from a different week still comes back to it, and an unmount
  // handler does not run on a hard close.
  //
  // The day itself is kept, not its Sunday. The week views only ever read
  // the week around it, so nothing changes for them; the day view needs to
  // know *which* day, and a week step keeps the weekday so that paging
  // forward from Tuesday and opening the day lands on next Tuesday.
  const goTo = useCallback((iso: string) => {
    if (!isDay(iso)) return;
    setFocus(iso);
    try {
      window.sessionStorage.setItem(WEEK_KEY, iso);
    } catch {
      // A browser refusing storage is not a reason to refuse navigation.
    }
  }, []);

  const setView = useCallback((next: BoardView) => {
    setViewState(next);
    try {
      window.localStorage.setItem(VIEW_KEY, next);
    } catch {
      // Likewise: the view still changes, it is only not remembered.
    }
  }, []);

  const previous = useCallback(
    () => goTo(stepFocus(view, focus, -1)),
    [goTo, view, focus],
  );
  const next = useCallback(
    () => goTo(stepFocus(view, focus, 1)),
    [goTo, view, focus],
  );
  const goToToday = useCallback(() => goTo(today), [goTo, today]);
  const openDay = useCallback(
    (iso: string) => {
      goTo(iso);
      setView("day");
    },
    [goTo, setView],
  );
  const openWeek = useCallback(
    (iso: string) => {
      goTo(iso);
      setView("week");
    },
    [goTo, setView],
  );

  /** Read one week, and resolve to how it should settle.
   *
   *  Deliberately *does not* call `setState` itself. The settle happens in
   *  the caller's `.then()`, which is what keeps the effect below out of the
   *  cascading-render pattern the compiler rejects — the same shape the
   *  original inline fetch had, with the token and the error arm factored
   *  out so the effect and `reloadWeek` cannot drift apart.
   *
   *  A failure resolves rather than rejects, and resolves *marked for this
   *  week*: the week is settled either way, so the board always leaves its
   *  loading state. A failure that left `for` behind `weekStart` would spin
   *  forever, which is the one outcome worse than the failure itself. */
  const fetchWeek = useCallback(async (wanted: string): Promise<WeekRead> => {
    const token = ++weekToken.current;
    try {
      const found = await scheduleAt(wanted);
      return { token, week: { for: wanted, schedule: found, error: null } };
    } catch (reason) {
      return {
        token,
        week: {
          for: wanted,
          schedule: null,
          error:
            reason instanceof Error && reason.message
              ? reason.message
              : "לא הצלחנו לטעון את הסידור",
        },
      };
    }
  }, []);

  /** Re-read the period covering the displayed week.
   *
   *  The overview hands over the *current* period, so the common case — a
   *  manager on this week — costs no extra request, and paging away is what
   *  fetches. */
  const reloadWeek = useCallback(async () => {
    const read = await fetchWeek(weekStart);
    if (read.token !== weekToken.current) return;
    setWeek(read.week);
  }, [fetchWeek, weekStart]);

  useEffect(() => {
    fetchWeek(weekStart).then((read) => {
      // The token, not a cleanup flag. A cleanup flag only covers the read
      // this effect started; the token also makes a `reloadWeek` begun
      // before the manager paged land as stale, and that one has no effect
      // body to hang a flag on.
      if (read.token === weekToken.current) setWeek(read.week);
    });
    // `scheduleId` is a dependency because a write to the current period
    // changes what `/at` answers for the week containing it — without it, a
    // freshly generated week would render against the pre-write copy.
  }, [fetchWeek, weekStart, scheduleId, refreshKey]);

  /** Read every period touching a span. The week read's twin, and settled
   *  the same way: by the caller, against the newest token, and marked for
   *  its span even when it failed so the view always leaves its loading
   *  state. */
  const fetchSpan = useCallback(
    async (start: string, end: string): Promise<SpanRead> => {
      const token = ++spanToken.current;
      const wanted = `${start}|${end}`;
      try {
        const found = await schedulesBetween(start, end);
        return {
          token,
          span: { for: wanted, schedules: found, error: null },
        };
      } catch (reason) {
        return {
          token,
          span: {
            for: wanted,
            schedules: NO_SCHEDULES,
            error:
              reason instanceof Error && reason.message
                ? reason.message
                : "לא הצלחנו לטעון את הסידור",
          },
        };
      }
    },
    [],
  );

  const reloadRange = useCallback(async () => {
    if (!spanKey) return;
    const read = await fetchSpan(range.start, range.end);
    if (read.token !== spanToken.current) return;
    setSpan(read.span);
  }, [fetchSpan, spanKey, range.start, range.end]);

  useEffect(() => {
    if (!spanKey) return;
    fetchSpan(range.start, range.end).then((read) => {
      if (read.token === spanToken.current) setSpan(read.span);
    });
  }, [fetchSpan, spanKey, range.start, range.end, scheduleId, refreshKey]);

  const refresh = useCallback(async (date?: string) => {
    const day = date || focus;
    const wantedRange = rangeOf(view, day);
    const [weekRead, spanRead] = await Promise.all([
      fetchWeek(sundayOf(day)),
      isOverview(view) ? fetchSpan(wantedRange.start, wantedRange.end) : Promise.resolve(null),
    ]);
    if (weekRead.token === weekToken.current) setWeek(weekRead.week);
    if (spanRead && spanRead.token === spanToken.current) setSpan(spanRead.span);
    const error = weekRead.week.error || spanRead?.span.error;
    if (error) throw new Error(error);
    // Navigate only after the updated data arrives, without undoing a newer navigation.
    if (weekRead.token === weekToken.current && (!spanRead || spanRead.token === spanToken.current)) goTo(day);
  }, [focus, view, fetchWeek, fetchSpan, goTo]);

  const setFilters = useCallback((next: Partial<BoardFilters>) => {
    setFiltersState((current) => ({ ...current, ...next }));
  }, []);

  const clearFilters = useCallback(() => setFiltersState(EMPTY_FILTERS), []);

  const filtersActive = useMemo(
    () =>
      filters.employee !== "" ||
      filters.role !== "" ||
      filters.shift !== "" ||
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

  // Settled only when the answer on hand is for the span on screen — the
  // same derivation the week uses, so a month paged away from never lends
  // its periods to the one being read.
  const spanSettled = spanKey !== null && span.for === spanKey;

  return {
    view,
    setView,
    focus,
    rangeStart: range.start,
    rangeEnd: range.end,
    weekStart,
    weekEnd,
    today,
    isCurrent: showsToday(view, focus, today),
    previous,
    next,
    goToToday,
    goToWeekOf: goTo,
    openDay,
    openWeek,
    filters,
    setFilters,
    clearFilters,
    filtersActive,
    // Derived rather than stored: the week is loading exactly while the
    // answer on hand is for a different week than the one on screen. One
    // source of truth, and no flag to get out of step with the data.
    weekSchedule: week.for === weekStart ? week.schedule : null,
    weekBusy: week.for !== weekStart,
    weekError: week.for === weekStart ? week.error : null,
    reloadWeek,
    rangeSchedules: spanSettled ? span.schedules : NO_SCHEDULES,
    rangeBusy: spanKey !== null && !spanSettled,
    rangeError: spanSettled ? span.error : null,
    reloadRange,
    refresh,
    check,
  };
}

/** The day the manager last had the board on this session, if any.
 *
 *  Read once at mount. A stored value that is not a date is discarded rather
 *  than trusted — `sessionStorage` is writable by anything on the origin,
 *  and a malformed day would render a board of `Invalid Date`. */
function readRememberedDay(): string | null {
  try {
    const stored = window.sessionStorage.getItem(WEEK_KEY);
    return stored && isDay(stored) ? stored : null;
  } catch {
    return null;
  }
}

/** The view the manager last chose in this browser, or the week.
 *
 *  The week is the default because it is the unit a schedule is built in:
 *  a manager who has never touched the switch should land on the board they
 *  can build on, not on an overview of it. */
function readRememberedView(): BoardView {
  try {
    const stored = window.localStorage.getItem(VIEW_KEY);
    return isBoardView(stored) ? stored : "week";
  } catch {
    return "week";
  }
}
