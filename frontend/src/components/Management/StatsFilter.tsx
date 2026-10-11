"use client";

import { CalendarCheck, ChevronLeft, ChevronRight, X } from "lucide-react";

import { DateInput } from "@/components/DateInput";

import type { DateRange, StatsFilter as Filter, StatsSpan } from "./statsRange";
import {
  STATS_SPANS,
  isSteppable,
  rangeLabel,
  showsToday,
  stepFocus,
} from "./statsRange";

/** What the stats panel is filtered to: a span of dates and, optionally, one
 *  person.
 *
 *  The two are independent on purpose. "דנה בחודש שעבר" and "כל הצוות היום"
 *  are both ordinary questions, and a control that reset the person whenever
 *  the dates moved would make the first one a three-step chore.
 *
 *  This picks; it does not count. Every choice here becomes a question for
 *  the server, and what comes back is rendered as it arrives.
 *
 *  The arrows are mirrored for RTL exactly as the board's `WeekNav` mirrors
 *  them: the previous span sits to the right, so the arrow pointing right
 *  goes back. */
export function StatsFilter({
  filter,
  range,
  today,
  people,
  hasPeriod,
  isDefault,
  onChange,
  onReset,
}: {
  filter: Filter;
  /** The dates the filter currently covers, or null when it names none. */
  range: DateRange | null;
  today: string;
  /** Everyone who can be picked, in the order they should be listed. */
  people: string[];
  /** Whether there is a stored period for "התקופה" to mean. */
  hasPeriod: boolean;
  /** Nothing is narrowed, so there is nothing for "איפוס" to undo. */
  isDefault: boolean;
  onChange: (next: Filter) => void;
  onReset: () => void;
}) {
  const steppable = isSteppable(filter.span);
  const spans = STATS_SPANS.filter((row) => row.id !== "period" || hasPeriod);

  const pickSpan = (span: StatsSpan) => {
    // A range opens on the dates already showing, so switching to it changes
    // the control and not the numbers until the manager edits a date.
    const seeded =
      span === "range" && range
        ? { from: range.start, to: range.end }
        : {};
    onChange({ ...filter, ...seeded, span });
  };

  return (
    <div className="stats-filter" role="group" aria-label="סינון הנתונים">
      <div className="stats-spans" role="group" aria-label="טווח זמן">
        {spans.map((row) => (
          <button
            key={row.id}
            type="button"
            className={
              row.id === filter.span ? "stats-span is-on" : "stats-span"
            }
            aria-pressed={row.id === filter.span}
            onClick={() => pickSpan(row.id)}
          >
            {row.label}
          </button>
        ))}
      </div>

      {filter.span === "range" ? (
        <div className="stats-dates">
          <label className="stats-field">
            <span>מ־</span>
            <DateInput
              className="stats-date"
              value={filter.from}
              max={filter.to || undefined}
              aria-label="מתאריך, בפורמט יום/חודש/שנה"
              onChange={(from) => onChange({ ...filter, from })}
            />
          </label>
          <label className="stats-field">
            <span>עד</span>
            <DateInput
              className="stats-date"
              value={filter.to}
              min={filter.from || undefined}
              aria-label="עד תאריך, בפורמט יום/חודש/שנה"
              onChange={(to) => onChange({ ...filter, to })}
            />
          </label>
        </div>
      ) : (
        <div className="stats-nav">
          {steppable ? (
            <button
              type="button"
              className="stats-nav-button"
              aria-label="הקודם"
              title="הקודם"
              onClick={() =>
                onChange({
                  ...filter,
                  focus: stepFocus(filter.span, filter.focus, -1),
                })
              }
            >
              <ChevronRight size={15} />
            </button>
          ) : null}
          <span className="stats-nav-label" aria-live="polite">
            {rangeLabel(filter.span, range) || "אין תקופה פתוחה"}
          </span>
          {steppable ? (
            <>
              <button
                type="button"
                className="stats-nav-button"
                aria-label="הבא"
                title="הבא"
                onClick={() =>
                  onChange({
                    ...filter,
                    focus: stepFocus(filter.span, filter.focus, 1),
                  })
                }
              >
                <ChevronLeft size={15} />
              </button>
              {/* Disabled rather than hidden when today is already showing,
                  so the control keeps its place — the same choice the
                  board's own "היום" makes. */}
              <button
                type="button"
                className="stats-today"
                disabled={showsToday(range, today)}
                onClick={() => onChange({ ...filter, focus: today })}
              >
                <CalendarCheck size={13} />
                היום
              </button>
            </>
          ) : null}
        </div>
      )}

      <label className="stats-field stats-person">
        <span>חייל/ת</span>
        <select
          className="stats-select"
          value={filter.employee}
          onChange={(event) =>
            onChange({ ...filter, employee: event.target.value })
          }
        >
          <option value="">כל הצוות</option>
          {people.map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </select>
      </label>

      {isDefault ? null : (
        <button type="button" className="stats-reset" onClick={onReset}>
          <X size={13} />
          איפוס
        </button>
      )}
    </div>
  );
}
