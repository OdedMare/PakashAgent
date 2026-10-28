"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import { useState } from "react";

const WEEKDAYS = ["א׳", "ב׳", "ג׳", "ד׳", "ה׳", "ו׳", "ש׳"];
const MONTH = new Intl.DateTimeFormat("he-IL", { month: "long", year: "numeric", timeZone: "UTC" });

/** A month of one weekend cycle, painted from the single fact typed into it.
 *
 *  Clicking any day says "group א closes this week's weekend"; that is the
 *  anchor, and every other weekend's owner follows from it the way the
 *  server derives it (`bl/rotation`). The painted days are a preview: the
 *  closure runs from `startDay` (days before Saturday) to the Sunday
 *  handover, and the group not closing is home for exactly those days. */
export function RotationCalendar({
  label,
  groups,
  anchor,
  startDay,
  onAnchor,
}: {
  label: string;
  groups: readonly string[];
  anchor: string;
  /** First closure day, as an offset from Saturday (-2 = Thursday). */
  startDay: number;
  onAnchor: (iso: string) => void;
}) {
  const [month, setMonth] = useState(() => (anchor || todayIso()).slice(0, 7));
  const anchorSaturday = anchor ? saturdayOf(anchor) : "";
  const today = todayIso();

  const closure = (iso: string) => {
    if (!anchorSaturday) return null;
    const weekday = weekdayOf(iso);
    // A Sunday is the handover of the weekend before it; every other day
    // belongs to the Saturday ending its own week.
    const saturday = weekday === 0 ? addDays(iso, -1) : addDays(iso, 6 - weekday);
    const offset = weekday === 0 ? 1 : weekday - 6;
    if (offset < startDay) return null;
    const weeks = Math.round((Date.parse(saturday) - Date.parse(anchorSaturday)) / (7 * 86400000));
    const index = ((weeks % groups.length) + groups.length) % groups.length;
    return { index, handover: offset === 1, saturday: offset === 0 };
  };

  const first = `${month}-01`;
  const lead = weekdayOf(first);
  const length = new Date(Date.UTC(Number(month.slice(0, 4)), Number(month.slice(5, 7)), 0)).getUTCDate();
  const cells = [
    ...Array.from({ length: lead }, () => ""),
    ...Array.from({ length }, (_, n) => addDays(first, n)),
  ];

  return (
    <div className="rotation-calendar" aria-label={`לוח הסגירות של ה${label}`}>
      <div className="rotation-calendar-head">
        <button type="button" className="icon-button subtle" aria-label="החודש הקודם" onClick={() => setMonth(shiftMonth(month, -1))}><ChevronRight size={16} /></button>
        <strong>{MONTH.format(new Date(`${first}T00:00:00Z`))}</strong>
        <button type="button" className="icon-button subtle" aria-label="החודש הבא" onClick={() => setMonth(shiftMonth(month, 1))}><ChevronLeft size={16} /></button>
      </div>
      <div className="rotation-calendar-grid" role="grid">
        {WEEKDAYS.map((day) => <span key={day} className="rotation-calendar-weekday" role="columnheader">{day}</span>)}
        {cells.map((iso, n) => {
          if (!iso) return <span key={`pad-${n}`} aria-hidden="true" />;
          const owner = closure(iso);
          const group = owner ? groups[owner.index] : "";
          return (
            <button
              type="button"
              key={iso}
              className={[
                "rotation-calendar-day",
                owner ? `is-group-${owner.index}` : "",
                owner?.handover ? "is-handover" : "",
                iso === today ? "is-today" : "",
              ].filter(Boolean).join(" ")}
              title={owner ? `${label} ${group}׳ ${owner.handover ? "— חילוף" : "סוגר"}` : `סימון: ${label} ${groups[0]}׳ סוגר את הסופ״ש הזה`}
              aria-pressed={Boolean(owner) && owner?.index === 0 && !owner.handover}
              onClick={() => onAnchor(saturdayOf(iso))}
            >
              <span>{Number(iso.slice(8))}</span>
              {owner?.saturday ? <small>{group}׳</small> : null}
            </button>
          );
        })}
      </div>
      {anchorSaturday ? (
        <div className="rotation-calendar-legend">
          {groups.map((group, index) => <span key={group}><i className={`is-group-${index}`} />{label} {group}׳ סוגר</span>)}
          <span><i className="is-handover" />חילוף בראשון</span>
        </div>
      ) : null}
    </div>
  );
}

function todayIso(): string {
  const now = new Date();
  return new Date(Date.UTC(now.getFullYear(), now.getMonth(), now.getDate())).toISOString().slice(0, 10);
}

function weekdayOf(iso: string): number {
  return new Date(`${iso}T00:00:00Z`).getUTCDay();
}

function saturdayOf(iso: string): string {
  return addDays(iso, 6 - weekdayOf(iso));
}

function addDays(iso: string, days: number): string {
  const [year, month, day] = iso.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day + days)).toISOString().slice(0, 10);
}

function shiftMonth(month: string, delta: number): string {
  const [year, value] = month.split("-").map(Number);
  return new Date(Date.UTC(year, value - 1 + delta, 1)).toISOString().slice(0, 7);
}
