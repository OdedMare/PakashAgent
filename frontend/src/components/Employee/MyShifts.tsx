"use client";

import { CalendarClock, ChevronDown, Clock3, Users } from "lucide-react";
import { useEffect, useState } from "react";

import { shortDate } from "@/components/DateInput";
import type { EmployeeView } from "@/types";

import { hoursLabel, splitByNow, timedShifts, untilLabel, type TimedShift } from "./shiftTimes";

/** The clock, re-read every minute so "בעוד 20 דקות" does not go stale on a
 *  screen left open, and a shift moves to "עכשיו" when it starts. */
function useNow(): Date {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 60_000);
    return () => window.clearInterval(timer);
  }, []);
  return now;
}

/** The "mine" tab's shift half: the next shift on top, then the list.
 *
 *  The card answers what nearly everyone opens this screen to ask — when am
 *  I on next, at what time, with whom — without reading a list. The list
 *  below holds what is still ahead; shifts already over fold away under one
 *  line, because last week's mornings were pushing next week's off a phone
 *  screen. Everything here is read from the view; nothing is recounted
 *  (the hours of a shift are the slot's own). */
export function MyShifts({ view }: { view: EmployeeView }) {
  const now = useNow();
  const shifts = timedShifts(view);
  const { current, next, upcoming, past } = splitByNow(shifts, now);

  if (shifts.length === 0) {
    return (
      <section className="employee-panel">
        <h2>המשמרות שלי</h2>
        <p className="employee-note">
          אין לך משמרות בתקופה הזו. אם זו טעות — כדאי לדבר עם המנהל.
        </p>
      </section>
    );
  }

  return (
    <>
      {current ? <NextShiftCard shift={current} now={now} live /> : null}
      {!current && next ? <NextShiftCard shift={next} now={now} /> : null}

      <section className="employee-panel">
        <h2>המשמרות שלי</h2>
        {upcoming.length ? (
          <ShiftList shifts={upcoming} highlight={(current ?? next)?.start} />
        ) : (
          <p className="employee-note">אין לך עוד משמרות בתקופה הזו.</p>
        )}
        {past.length ? (
          <details className="shift-past">
            <summary>
              <ChevronDown size={15} aria-hidden="true" />
              {past.length === 1 ? "משמרת אחת שעברה" : `${past.length} משמרות שעברו`}
            </summary>
            <ShiftList shifts={past} />
          </details>
        ) : null}
      </section>
    </>
  );
}

/** The one shift that matters right now. `live` while it is under way. */
function NextShiftCard({ shift, now, live = false }: { shift: TimedShift; now: Date; live?: boolean }) {
  const hours = hoursLabel(shift);
  return (
    <section className={live ? "next-shift is-live" : "next-shift"} aria-label="המשמרת הבאה שלי">
      <div className="next-shift-head">
        <span className="next-shift-eyebrow">
          <CalendarClock size={14} aria-hidden="true" />
          {live ? "במשמרת עכשיו" : "המשמרת הבאה שלי"}
        </span>
        <span className="next-shift-until">
          {live ? (shift.endTime ? `עד ${shift.endTime}` : "היום") : untilLabel(shift.start, now)}
        </span>
      </div>
      <div className="next-shift-when">
        <strong>{shift.shift}</strong>
        <span>
          {shift.weekday} · {shortDate(shift.date)}
        </span>
      </div>
      <div className="next-shift-details">
        {hours ? (
          <span>
            <Clock3 size={14} aria-hidden="true" />
            <bdi>{hours}</bdi>
          </span>
        ) : null}
        {shift.is_on_call ? <span className="shift-oncall">כוננות</span> : null}
        {shift.with.length ? (
          <span>
            <Users size={14} aria-hidden="true" />
            עם {shift.with.join(", ")}
          </span>
        ) : null}
      </div>
    </section>
  );
}

function ShiftList({ shifts, highlight }: { shifts: TimedShift[]; highlight?: Date }) {
  return (
    <ul className="shift-list">
      {shifts.map((shift) => {
        const hours = hoursLabel(shift);
        const isNext = highlight !== undefined && shift.start.getTime() === highlight.getTime();
        return (
          <li key={`${shift.date}-${shift.shift}`} className={isNext ? "is-next" : undefined}>
            <div className="shift-when">
              <strong>{shift.weekday}</strong>
              <span>{shortDate(shift.date)}</span>
            </div>
            <div className="shift-what">
              <span className="shift-name">{shift.shift}</span>
              {hours ? <bdi className="shift-hours">{hours}</bdi> : null}
              {shift.is_on_call ? <span className="shift-oncall">כוננות</span> : null}
              {shift.with.length > 0 ? (
                <span className="shift-with">עם {shift.with.join(", ")}</span>
              ) : null}
            </div>
          </li>
        );
      })}
    </ul>
  );
}
