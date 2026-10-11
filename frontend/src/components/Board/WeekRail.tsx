"use client";

import { hebrewWeekday } from "@/components/Management/Calendar";
import { displayDate } from "@/components/DateInput";
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
  selected,
  onPickDay,
}: {
  weekStart: string;
  today: string;
  schedule: Schedule | null;
  /** The one day the board below is showing, when it is showing one. Marked
   *  on the rail so the week around a day view stays readable as a week —
   *  the rail is then what says which of the seven the grid is. */
  selected?: string;
  /** Open a day from the rail. When given, each segment is a button; the
   *  rail already names every day of the week, so it is the nearest thing
   *  the board has to a date picker and costs no new control. */
  onPickDay?: (date: string) => void;
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
      <div className="week-rail-days" role={onPickDay ? "group" : "list"}>
        {days.map((day) => {
          const className = [
            "week-rail-day",
            `is-${busy ? "loading" : day.tone}`,
            day.date === today ? "is-today" : "",
            day.date === selected ? "is-selected" : "",
          ]
            .filter(Boolean)
            .join(" ");
          const label = `${hebrewWeekday(day.date)} ${displayDate(day.date)}: ${busy ? "נטען" : dayLabel(day)}`;
          // Spans rather than divs inside, so the same body is valid in the
          // button a pickable day becomes.
          const body = (
            <>
              <span className="week-rail-day-head">
                <strong>{hebrewWeekday(day.date)}</strong>
                <span>{displayDate(day.date)}</span>
              </span>
              <span className="week-rail-track" aria-hidden="true">
                <span style={{ width: busy ? "0%" : `${day.percent}%` }} />
              </span>
              <small>{busy ? "טוען…" : dayLabel(day)}</small>
            </>
          );
          return onPickDay ? (
            <button
              key={day.date}
              type="button"
              className={className}
              aria-label={label}
              aria-pressed={day.date === selected}
              title="פתיחת היום"
              onClick={() => onPickDay(day.date)}
            >
              {body}
            </button>
          ) : (
            <div
              key={day.date}
              className={className}
              role="listitem"
              aria-label={label}
            >
              {body}
            </div>
          );
        })}
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
