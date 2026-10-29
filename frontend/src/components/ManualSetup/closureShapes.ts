/** The round types the rotation screen offers, as stored window rows.
 *
 *  A window row is days relative to the closing Saturday (-6 is the Sunday
 *  before it, 1 the Sunday after) plus clock times; the server reads nothing
 *  else. A type is only a way of filling that row in, so a row typed by hand
 *  and a row picked from a type are the same thing to a build.
 *
 *  A type is named by the day the closure opens: the group that is not
 *  closing is home from then until the Sunday handover, so in a round's two
 *  weeks that day sets the days on base and at home — Thursday is 11/3,
 *  Friday 12/2, Wednesday 10/4. A week on, week off opens at the handover
 *  itself, so a week-long closure never overlaps the one it follows. */

import type { RotationClosureWindow } from "@/types";

export type Shape = "thursday" | "friday" | "wednesday" | "week" | "custom";

export const SHAPES: Shape[] = ["thursday", "friday", "wednesday", "week", "custom"];

export const DAY_NAMES = ["ראשון", "שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת"];

const OPENS: Record<Exclude<Shape, "custom">, number> = { thursday: -2, friday: -1, wednesday: -3, week: -6 };
const SPLITS: Record<Exclude<Shape, "custom">, string> = { thursday: "11/3", friday: "12/2", wednesday: "10/4", week: "שבוע־שבוע" };

/** How a type reads on its button. The day split is a round's (two weeks);
 *  a triplet's or a רבעון's weeks would split differently, so they read by days. */
export function shapeLabel(shape: Shape, groups: number): { title: string; detail: string } {
  if (shape === "custom") return { title: "ימים ושעות אחרים", detail: "בוחרים בעצמכם יום ושעה לכניסה וליציאה." };
  const span = shape === "week" ? "מראשון עד ראשון" : `מ${DAY_NAMES[OPENS[shape] + 6]} עד ראשון`;
  if (groups > 2) return { title: shape === "week" ? `שבוע בבסיס, ${groups === 3 ? "שבועיים" : `${groups - 1} שבועות`} בבית` : span, detail: shape === "week" ? "חילוף ביום ראשון." : "הסגירה בסופ״ש." };
  const [base, home] = SPLITS[shape].split("/");
  return {
    title: SPLITS[shape],
    detail: shape === "week" ? "שבוע בבסיס, שבוע בבית · חילוף בראשון." : `${base} ימים בבסיס, ${home} בבית · סגירה ${span}.`,
  };
}

/** The row a type stands for, or null for 11/3 when it is the cycle's
 *  regular hours: that is the server's default, so no row is written. */
export function shapeRow(shape: Shape, handover: string, base: Partial<RotationClosureWindow>, explicit = false): Partial<RotationClosureWindow> | null {
  const end = handover || "00:00";
  if (shape === "custom") return { ...base, start_day: base.start_day ?? -2, start_time: base.start_time || "00:00", end_day: base.end_day ?? 1, end_time: base.end_time || end };
  if (shape === "thursday" && !explicit) return null;
  return { ...base, start_day: OPENS[shape], start_time: shape === "week" ? end : "00:00", end_day: 1, end_time: end };
}

/** Which type a stored row reads as. A row whose times were adjusted away
 *  from the type's own clock is "custom", so nothing is hidden. */
export function shapeOf(row: RotationClosureWindow | undefined, handover: string): Shape {
  if (!row) return "thursday";
  const same = (shape: Shape) => {
    const expected = shapeRow(shape, handover, {}, true)!;
    return (["start_day", "start_time", "end_day", "end_time"] as const).every((key) => expected[key] === row[key]);
  };
  return SHAPES.filter((shape) => shape !== "custom").find(same) ?? "custom";
}

/** "משישי 00:00 עד ראשון שאחרי 16:00" — a window in words. */
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
