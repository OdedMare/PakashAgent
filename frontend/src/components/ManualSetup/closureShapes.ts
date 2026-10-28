/** The closure shapes the rotation screen offers, as stored window rows.
 *
 *  A window row is days relative to the closing Saturday (-6 is the Sunday
 *  before it, 1 the Sunday after) plus clock times; the server reads nothing
 *  else. The shapes here are only ways of filling that row in, so a row typed
 *  by hand and a row picked from a shape are the same thing to a build. */

import type { RotationClosureWindow } from "@/types";

export type Shape = "thursday" | "friday" | "week" | "custom";

/** The clock a closure turns over on: the end of the day's first shift, so
 *  the leaving group still holds Sunday morning (the handover) and the next
 *  one takes over from there. Starts open on the first shift's start, so a
 *  night shift ending then belongs to nobody's closure. */
export interface Clock { start: string; end: string }

export const DAY_NAMES = ["ראשון", "שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת"];

export function shapeLabel(shape: Shape, groups: number): { title: string; detail: string } {
  switch (shape) {
    case "thursday": return { title: "חמישי עד ראשון", detail: "סופ״ש ארוך — הסגירה מתחילה בחמישי ונגמרת בחילוף של ראשון." };
    case "friday": return { title: "שישי עד ראשון", detail: "סופ״ש קצר — חמישי הוא יום עבודה רגיל לכולם." };
    case "week": return { title: groups > 2 ? "שבוע בבסיס, שבועיים בבית" : "שבוע בבסיס, שבוע בבית", detail: "הקבוצה בבסיס מראשון עד ראשון, והחילוף ביום ראשון." };
    default: return { title: "ימים ושעות אחרים", detail: "בוחרים בעצמכם יום ושעה לכניסה וליציאה." };
  }
}

/** The row a shape stands for, or null for the default (no row at all). */
export function shapeRow(shape: Shape, clock: Clock, base: Partial<RotationClosureWindow>, withDefault = false): Partial<RotationClosureWindow> | null {
  switch (shape) {
    case "thursday": return withDefault ? { ...base, start_day: -2, start_time: clock.start, end_day: 1, end_time: clock.end } : null;
    case "friday": return { ...base, start_day: -1, start_time: clock.start, end_day: 1, end_time: clock.end };
    case "week": return { ...base, start_day: -6, start_time: clock.end, end_day: 1, end_time: clock.end };
    default: return { ...base, start_day: base.start_day ?? -2, start_time: base.start_time || clock.start, end_day: base.end_day ?? 1, end_time: base.end_time || clock.end };
  }
}

/** Which shape a stored row reads as. A row whose times were adjusted away
 *  from the shape's own clock is still "custom", so nothing is hidden. */
export function shapeOf(row: RotationClosureWindow | undefined, clock: Clock): Shape {
  if (!row) return "thursday";
  const same = (shape: Shape) => {
    const expected = shapeRow(shape, clock, {}, true);
    return expected && (["start_day", "start_time", "end_day", "end_time"] as const).every((key) => expected[key] === row[key]);
  };
  return (["thursday", "friday", "week"] as Shape[]).find(same) ?? "custom";
}

/** "משישי 08:00 עד ראשון 16:00" — a window in words. */
export function windowSentence(row: Pick<RotationClosureWindow, "start_day" | "start_time" | "end_day" | "end_time">): string {
  return `מ${dayName(row.start_day)} ${row.start_time} עד ${dayName(row.end_day)} ${row.end_time}`;
}

function dayName(offset: number): string {
  // Offsets count from Saturday; the Sunday after it is offset 1.
  return DAY_NAMES[((offset + 6) % 7 + 7) % 7] + (offset > 0 ? " שאחרי" : "");
}

/** The Saturday closing the Sunday-to-Saturday week `iso` falls in — the
 *  same normalisation the server applies to a typed anchor. */
export function saturdayOf(iso: string): string {
  const day = new Date(`${iso}T00:00:00Z`).getUTCDay();
  return Number.isNaN(day) ? "" : addDays(iso, 6 - day);
}

export function addDays(iso: string, days: number): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!match) return "";
  return new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3]) + days)).toISOString().slice(0, 10);
}

/** The clock a unit's shifts turn over on (see `Clock`). */
export function clockOf(shifts: { start_time?: unknown; end_time?: unknown }[]): Clock {
  const timed = shifts
    .map((shift) => ({ start: String(shift.start_time ?? ""), end: String(shift.end_time ?? "") }))
    .filter((shift) => /^\d{2}:\d{2}$/.test(shift.start) && /^\d{2}:\d{2}$/.test(shift.end))
    .sort((a, b) => a.start.localeCompare(b.start));
  return timed[0] ?? { start: "08:00", end: "12:00" };
}
