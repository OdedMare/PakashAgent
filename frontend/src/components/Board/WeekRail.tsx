"use client";

import { formatDate, hebrewWeekday } from "@/components/Management/Calendar";
import type { Schedule } from "@/types";

import { weekDates } from "./useBoard";

/** The product's signature: one factual line for the whole week.
 *
 * It is deliberately not another dashboard chart. Each segment is a day the
 * manager already works with, and its fill is assigned headcount out of
 * required headcount. Colour is reserved for a shortage or a real audit
 * warning. The rail stays useful when no schedule exists by naming every day
 * as not planned instead of rendering invented zeroes as performance data. */
export function WeekRail({
  weekStart,
  today,
  schedule,
  busy = false,
}: {
  weekStart: string;
  today: string;
  schedule: Schedule | null;
  /** The week's schedule is still being read.
   *
   *  The rail renders from `weekStart` alone, so it is already correct for
   *  the newly selected week the moment the manager pages — which is the
   *  point, the dates must move immediately. But its *fills* come from a
   *  schedule that has not arrived, and "לא תוכנן" on every day is a
   *  factual claim about a week nobody has read yet. While this is set the
   *  rail names the days and says it is still counting. */
  busy?: boolean;
}) {
  const days = weekDates(weekStart).map((date) => {
    const required = (schedule?.slots ?? [])
      .filter((slot) => slot.slot_date === date)
      .reduce((sum, slot) => sum + (slot.headcount || 0), 0);
    const warnings = (schedule?.warnings ?? []).filter(
      (warning) => warning.date === date && warning.severity === "warning",
    ).length;
    // Seats short, summed from the audit's own per-slot `unfilled` counts
    // rather than from the number of assignment rows on the date. Two things
    // that count of bodies gets wrong, and this rail is the one line a
    // manager reads the whole week off: somebody shadowing a shift is a body
    // who is not a seat, and a slot doubled up lends its spare body to the
    // slot beside it — so a day with one shift overstaffed and another
    // entirely empty filled its bar to 100%.
    const missing = (schedule?.warnings ?? [])
      .filter((warning) => warning.code === "unfilled" && warning.date === date)
      .reduce((sum, warning) => {
        const short =
          Number(warning.details?.required) - Number(warning.details?.assigned);
        return sum + (Number.isFinite(short) ? Math.max(0, short) : 0);
      }, 0);
    const assigned = Math.max(0, required - missing);
    const percent = required
      ? Math.min(100, Math.round((assigned / required) * 100))
      : 0;

    return {
      assigned,
      date,
      missing,
      percent,
      required,
      warnings,
      tone: warnings ? "warning" : missing ? "short" : required ? "ready" : "quiet",
    };
  });

  return (
    <section
      className="week-rail"
      aria-label="מוכנות לפי יום"
      aria-busy={busy || undefined}
    >
      <div className="week-rail-label">
        <strong>מסילת השבוע</strong>
        <span>{busy ? "טוען…" : "איוש מול צורך"}</span>
      </div>
      <div className="week-rail-days" role="list">
        {days.map((day) => (
          <div
            key={day.date}
            className={`week-rail-day is-${busy ? "loading" : day.tone}${day.date === today ? " is-today" : ""}`}
            role="listitem"
            aria-label={`${hebrewWeekday(day.date)} ${formatDate(day.date)}: ${busy ? "נטען" : dayLabel(day)}`}
          >
            <div className="week-rail-day-head">
              <strong>{hebrewWeekday(day.date)}</strong>
              <span>{formatDate(day.date)}</span>
            </div>
            <div className="week-rail-track" aria-hidden="true">
              <span style={{ width: busy ? "0%" : `${day.percent}%` }} />
            </div>
            <small>{busy ? "טוען…" : dayLabel(day)}</small>
          </div>
        ))}
      </div>
    </section>
  );
}

function dayLabel(day: {
  assigned: number;
  missing: number;
  required: number;
  warnings: number;
}): string {
  if (!day.required) return "לא תוכנן";
  if (day.warnings) return `${day.warnings} דורש טיפול`;
  if (day.missing) return `חסרים ${day.missing}`;
  return `${day.assigned}/${day.required} מוכן`;
}
