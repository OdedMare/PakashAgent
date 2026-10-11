import {
  addDays,
  addMonths,
  isDay,
  monthBounds,
  sundayOf,
} from "@/components/Board/dates";
import { hebrewWeekday } from "@/components/Management/Calendar";
import { displayDate, shortDate } from "@/components/DateInput";

/** What the stats panel is asked about.
 *
 *  `period` is the stored period the overview already counted, and it is the
 *  default because it is the one answer that costs no request. The other
 *  four are dates the manager picks, and none of them is a stored period: a
 *  day sits inside one, a month runs across several.
 *
 *  A month here is the calendar month, the 1st to its last day. The board's
 *  month view draws whole weeks instead and so starts before the 1st — right
 *  for a grid, wrong for a count, where "October" including four days of
 *  September would be a number nobody asked for. */
export type StatsSpan = "period" | "day" | "week" | "month" | "range";

export const STATS_SPANS: { id: StatsSpan; label: string }[] = [
  { id: "period", label: "התקופה" },
  { id: "day", label: "יום" },
  { id: "week", label: "שבוע" },
  { id: "month", label: "חודש" },
  { id: "range", label: "טווח" },
];

export interface StatsFilter {
  span: StatsSpan;
  /** The date a day, week or month is anchored on. */
  focus: string;
  /** The two ends of a chosen range. Either may be empty mid-edit. */
  from: string;
  to: string;
  /** One person, or empty for the whole team. */
  employee: string;
}

export interface DateRange {
  start: string;
  end: string;
}

/** The dates a filter covers, or null when it does not name any yet.
 *
 *  Null is a real state and not an error: a range whose second date has not
 *  been typed, or the `period` span on a workplace with nothing built. The
 *  panel says so instead of asking the server about half a range. */
export function rangeOf(
  filter: StatsFilter,
  period: DateRange | null,
): DateRange | null {
  if (filter.span === "period") return period;
  if (filter.span === "range") {
    if (!isDay(filter.from) || !isDay(filter.to)) return null;
    if (filter.from > filter.to) return null;
    return { start: filter.from, end: filter.to };
  }
  if (!isDay(filter.focus)) return null;
  if (filter.span === "day") return { start: filter.focus, end: filter.focus };
  if (filter.span === "week") {
    const sunday = sundayOf(filter.focus);
    return { start: sunday, end: addDays(sunday, 6) };
  }
  const month = monthBounds(filter.focus);
  return { start: month.first, end: month.last };
}

/** Where the anchor lands one step back (-1) or forward (+1) — the span's
 *  own width, so the arrows never show a date twice or skip one. */
export function stepFocus(
  span: StatsSpan,
  focus: string,
  direction: -1 | 1,
): string {
  if (span === "day") return addDays(focus, direction);
  if (span === "week") return addDays(focus, 7 * direction);
  if (span === "month") return addMonths(focus, direction);
  return focus;
}

/** Whether the arrows mean anything: a day, a week and a month have a next
 *  one. A stored period and a hand-picked range do not. */
export function isSteppable(span: StatsSpan): boolean {
  return span === "day" || span === "week" || span === "month";
}

/** The span in words, for the line between the arrows. */
export function rangeLabel(span: StatsSpan, range: DateRange | null): string {
  if (!range) return "";
  if (span === "day") {
    return `${hebrewWeekday(range.start)} ${displayDate(range.start)}`;
  }
  if (span === "month") {
    return new Date(`${range.start}T00:00:00`).toLocaleDateString("he-IL", {
      month: "long",
      year: "numeric",
    });
  }
  if (range.start === range.end) return displayDate(range.start);
  // The year once, at the end, when both ends share it.
  const sameYear = range.start.slice(0, 4) === range.end.slice(0, 4);
  const first = sameYear ? shortDate(range.start) : displayDate(range.start);
  return `${first}–${displayDate(range.end)}`;
}

/** Whether a span is the one today falls in, which is what "היום" returns
 *  to and therefore when that button has nothing to do. */
export function showsToday(range: DateRange | null, today: string): boolean {
  return Boolean(range && range.start <= today && today <= range.end);
}
