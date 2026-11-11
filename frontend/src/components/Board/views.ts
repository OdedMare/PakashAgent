import { addDays, addMonths, monthBounds, sundayOf } from "./dates";

/** How much of the calendar the board shows at once.
 *
 *  Four spans, and they fall into two kinds that behave differently on
 *  purpose:
 *
 *  - **`day` and `week` are the working board.** Both sit inside one stored
 *    period, so everything the board does — placing, dragging, clearing,
 *    publishing — is there, aimed at that period. A day is the week with six
 *    columns put away, not a second screen.
 *  - **`fortnight` and `month` are for reading.** They cross periods, and a
 *    write has to name the one period it lands on
 *    ([D12](../../../docs/DECISIONS.md#d12--dragging-a-shift-is-a-proposal-not-an-edit),
 *    [D18](../../../docs/DECISIONS.md#d18--the-boss-can-place-a-shift-without-the-agent-️-completes-d6)).
 *    So they draw the span and open a day or a week on click — the way a
 *    month in any calendar is where you find the day, not where you edit it.
 */
export type BoardView = "day" | "week" | "fortnight" | "month";

export const BOARD_VIEWS: { id: BoardView; label: string }[] = [
  { id: "day", label: "יום" },
  { id: "week", label: "שבוע" },
  { id: "fortnight", label: "שבועיים" },
  { id: "month", label: "חודש" },
];

export function isBoardView(value: unknown): value is BoardView {
  return BOARD_VIEWS.some((row) => row.id === value);
}

/** Whether a view spans more than one period and is therefore read-only. */
export function isOverview(view: BoardView): boolean {
  return view === "fortnight" || view === "month";
}

/** The dates a view draws, given the day it is anchored on.
 *
 *  Every span but a single day runs Sunday to Saturday in whole weeks. A
 *  month therefore starts before the 1st and ends after the last whenever
 *  those fall mid-week: the grid is weeks, and a week cut off at the month's
 *  edge would hide the days a shift pattern actually continues through. */
export function rangeOf(
  view: BoardView,
  focus: string,
): { start: string; end: string } {
  if (view === "day") return { start: focus, end: focus };
  const sunday = sundayOf(focus);
  if (view === "week") return { start: sunday, end: addDays(sunday, 6) };
  if (view === "fortnight") return { start: sunday, end: addDays(sunday, 13) };
  const month = monthBounds(focus);
  return {
    start: sundayOf(month.first),
    end: addDays(sundayOf(month.last), 6),
  };
}

/** Where the anchor lands one step back (-1) or forward (+1).
 *
 *  A step is the view's own width, so the arrows never show a date twice or
 *  skip one. The weekday is kept across a week step — a manager on Tuesday
 *  who pages forward and opens the day view is on next Tuesday. */
export function stepFocus(
  view: BoardView,
  focus: string,
  direction: -1 | 1,
): string {
  if (view === "day") return addDays(focus, direction);
  if (view === "week") return addDays(focus, 7 * direction);
  if (view === "fortnight") return addDays(focus, 14 * direction);
  return addMonths(focus, direction);
}

/** Whether the span on screen is the one today is in.
 *
 *  A month is compared by month and not by its drawn range: the grid of
 *  September ends on the first days of October, and calling that "the
 *  current month" on the 2nd would disable the button that leads to it. */
export function showsToday(
  view: BoardView,
  focus: string,
  today: string,
): boolean {
  if (view === "month") return focus.slice(0, 7) === today.slice(0, 7);
  const range = rangeOf(view, focus);
  return range.start <= today && today <= range.end;
}
