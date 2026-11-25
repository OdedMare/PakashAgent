"use client";

import { ArrowLeftRight, CalendarClock, CalendarX, ChevronDown, Clock3, Users } from "lucide-react";
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
export function MyShifts({
  view,
  onCantMake,
  onSwap,
}: {
  view: EmployeeView;
  /** Open the constraint request on this date and shift. */
  onCantMake: (date: string, shift: string) => void;
  /** Open the swap offer with this assignment as my half. */
  onSwap: (assignmentId: string) => void;
}) {
  const now = useNow();
  const shifts = timedShifts(view);
  const { current, next, upcoming, past } = splitByNow(shifts, now);
  // My own assignment per shift, which the swap form names by id.
  const assignmentOf = new Map(
    (view.schedule?.assignments ?? [])
      .filter((row) => row.employee === view.employee)
      .map((row) => [`${row.date}|${row.shift}`, row.id]),
  );
  // Asking is for a shift that has not started: one under way or over is
  // past the point a request could change anything.
  const actionsFor = (shift: TimedShift): ShiftActionProps | undefined => {
    if (shift.start.getTime() <= now.getTime()) return undefined;
    const assignmentId = assignmentOf.get(`${shift.date}|${shift.shift}`);
    return {
      label: `${shift.weekday} ${shortDate(shift.date)} · ${shift.shift}`,
      onCantMake: () => onCantMake(shift.date, shift.shift),
      onSwap: assignmentId ? () => onSwap(assignmentId) : undefined,
    };
  };

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
      {!current && next ? <NextShiftCard shift={next} now={now} actions={actionsFor(next)} /> : null}

      <section className="employee-panel">
        <h2>המשמרות שלי</h2>
        {upcoming.length ? (
          <ShiftList shifts={upcoming} highlight={(current ?? next)?.start} actionsFor={actionsFor} />
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
function NextShiftCard({
  shift,
  now,
  live = false,
  actions,
}: {
  shift: TimedShift;
  now: Date;
  live?: boolean;
  actions?: ShiftActionProps;
}) {
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
      {actions ? <ShiftActions {...actions} wide /> : null}
    </section>
  );
}

interface ShiftActionProps {
  /** Names the shift for a screen reader, since the visible text does not. */
  label: string;
  onCantMake: () => void;
  onSwap?: () => void;
}

/** Ask about this one shift: not to be on it, or to trade it.
 *
 *  Both open a form already filled in — the same forms as "בקשות והחלפות",
 *  so this is a shortcut to a request, never a change (D14). The manager
 *  still decides, and the forms say so where they are sent. */
function ShiftActions({ label, onCantMake, onSwap, wide = false }: ShiftActionProps & { wide?: boolean }) {
  return (
    <div className={wide ? "shift-actions is-wide" : "shift-actions"}>
      <button type="button" className="ghost-button" onClick={onCantMake} aria-label={`לא יכול/ה להגיע · ${label}`}>
        <CalendarX size={14} aria-hidden="true" />
        לא יכול/ה
      </button>
      {onSwap ? (
        <button type="button" className="ghost-button" onClick={onSwap} aria-label={`בקשת החלפה · ${label}`}>
          <ArrowLeftRight size={14} aria-hidden="true" />
          החלפה
        </button>
      ) : null}
    </div>
  );
}

function ShiftList({
  shifts,
  highlight,
  actionsFor,
}: {
  shifts: TimedShift[];
  highlight?: Date;
  actionsFor?: (shift: TimedShift) => ShiftActionProps | undefined;
}) {
  return (
    <ul className="shift-list">
      {shifts.map((shift) => {
        const hours = hoursLabel(shift);
        const isNext = highlight !== undefined && shift.start.getTime() === highlight.getTime();
        const actions = actionsFor?.(shift);
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
            {actions ? <ShiftActions {...actions} /> : null}
          </li>
        );
      })}
    </ul>
  );
}
