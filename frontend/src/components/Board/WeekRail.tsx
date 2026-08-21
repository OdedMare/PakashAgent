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
}: {
  weekStart: string;
  today: string;
  schedule: Schedule | null;
}) {
  const days = weekDates(weekStart).map((date) => {
    const required = (schedule?.slots ?? [])
      .filter((slot) => slot.slot_date === date)
      .reduce((sum, slot) => sum + (slot.headcount || 0), 0);
    const assigned = (schedule?.assignments ?? []).filter(
      (assignment) => assignment.date === date,
    ).length;
    const warnings = (schedule?.warnings ?? []).filter(
      (warning) => warning.date === date && warning.severity === "warning",
    ).length;
    const missing = Math.max(0, required - assigned);
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
    <section className="week-rail" aria-label="מוכנות לפי יום">
      <div className="week-rail-label">
        <strong>מסילת השבוע</strong>
        <span>איוש מול צורך</span>
      </div>
      <div className="week-rail-days" role="list">
        {days.map((day) => (
          <div
            key={day.date}
            className={`week-rail-day is-${day.tone}${day.date === today ? " is-today" : ""}`}
            role="listitem"
            aria-label={`${hebrewWeekday(day.date)} ${formatDate(day.date)}: ${dayLabel(day)}`}
          >
            <div className="week-rail-day-head">
              <strong>{hebrewWeekday(day.date)}</strong>
              <span>{formatDate(day.date)}</span>
            </div>
            <div className="week-rail-track" aria-hidden="true">
              <span style={{ width: `${day.percent}%` }} />
            </div>
            <small>{dayLabel(day)}</small>
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
