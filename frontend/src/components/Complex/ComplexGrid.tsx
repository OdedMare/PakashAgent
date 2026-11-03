"use client";

import { AlertTriangle, LogIn, MessagesSquare, Users } from "lucide-react";
import type { CSSProperties } from "react";

import { shortDate } from "@/components/DateInput";
import { hebrewWeekday, isWeekend } from "@/components/Management/Calendar";
import { colorStyle } from "@/components/Management/palette";

import { readCell, shiftsOf, type Focus, type Unit } from "./figures";

/** Every משמרת of the מכלול on one grid: a band per משמרת, a row per shift
 *  type, a column per day, the same cards and colours the משמרת's own board
 *  draws. It reads; it never writes — "כניסה לניהול" on a band's head is
 *  the way to change anything, inside that משמרת (D43). */
export function ComplexGrid({
  units,
  days,
  today,
  focus,
  dark,
  hueOf,
  busy,
  onFocusShift,
  onEnter,
  onChat,
}: {
  units: Unit[];
  days: string[];
  today: string;
  focus: Focus;
  dark: boolean;
  hueOf: (name: string) => number;
  busy: boolean;
  onFocusShift: (unit: string, shift: string) => void;
  onEnter: (unit: string) => void;
  onChat: (unit: string) => void;
}) {
  const bands = units
    .map((unit) => ({ unit, rows: rowsOf(unit, days, focus) }))
    .filter((band) => band.rows.length > 0 || (!focus.soldier && !focus.gapsOnly));
  if (bands.length === 0) {
    return <p className="cmd-empty">אין שורות שמתאימות לסינון בטווח שעל המסך.</p>;
  }
  return (
    <div className="board-grid-wrap">
      <div className="board-grid-scroll" data-tour="cmd-grid">
        <div
          className="board-grid cmd-grid"
          style={{ "--board-days": days.length } as CSSProperties}
          role="table"
          aria-label="לוח המכלול"
        >
          <div className="board-corner" role="columnheader">משמרת</div>
          {days.map((day) => (
            <div
              key={day}
              role="columnheader"
              className={[
                "board-dayhead",
                day === today ? "is-today" : "",
                isWeekend(day) ? "is-weekend" : "",
              ].filter(Boolean).join(" ")}
            >
              <span className="board-dayhead-weekday">{hebrewWeekday(day)}</span>
              <span className="board-dayhead-date">{shortDate(day)}</span>
              {day === today ? <span className="board-dayhead-pill">היום</span> : null}
              <DayCoverage units={bands.map((band) => band.unit)} day={day} focus={focus} />
            </div>
          ))}

          {bands.map(({ unit, rows }) => (
            <UnitBand
              key={unit.id}
              unit={unit}
              shifts={rows}
              days={days}
              today={today}
              focus={focus}
              dark={dark}
              hueOf={hueOf}
              busy={busy}
              onFocusShift={onFocusShift}
              onEnter={onEnter}
              onChat={onChat}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

/** The shift rows of one משמרת the filters leave in. */
function rowsOf(unit: Unit, days: string[], focus: Focus): string[] {
  return shiftsOf(unit).filter((name) => {
    if (focus.shift && name !== focus.shift) return false;
    const cells = days.map((day) => readCell(unit, name, day));
    if (focus.soldier) {
      const [id, ...rest] = focus.soldier.split(":");
      const who = rest.join(":");
      if (id !== unit.id || !cells.some((cell) => cell?.names.includes(who))) return false;
    }
    if (focus.gapsOnly && !cells.some((cell) => cell && cell.seats > cell.filled)) return false;
    return true;
  });
}

/** "filled/seats" for a day over what is on screen — the board's own pill. */
function DayCoverage({ units, day, focus }: { units: Unit[]; day: string; focus: Focus }) {
  let seats = 0;
  let filled = 0;
  for (const unit of units) {
    for (const shift of shiftsOf(unit)) {
      if (focus.shift && shift !== focus.shift) continue;
      const cell = readCell(unit, shift, day);
      if (!cell) continue;
      seats += cell.seats;
      filled += Math.min(cell.filled, cell.seats || cell.filled);
    }
  }
  if (!seats) return null;
  return (
    <span className={`board-dayhead-coverage${filled < seats ? " is-short" : ""}`} title="מאוישים מתוך המקומות">
      {filled}/{seats}
    </span>
  );
}

function UnitBand({
  unit, shifts, days, today, focus, dark, hueOf, busy, onFocusShift, onEnter, onChat,
}: {
  unit: Unit;
  shifts: string[];
  days: string[];
  today: string;
  focus: Focus;
  dark: boolean;
  hueOf: (name: string) => number;
  busy: boolean;
  onFocusShift: (unit: string, shift: string) => void;
  onEnter: (unit: string) => void;
  onChat: (unit: string) => void;
}) {
  const touching = unit.periods.filter((p) => p.starts_on <= days[days.length - 1] && p.ends_on >= days[0]);
  const status = touching.length === 0
    ? { label: "לא תוכנן", tone: "" }
    : touching.every((p) => p.status === "published")
      ? { label: "פורסם", tone: "published" }
      : { label: "טיוטה", tone: "draft" };
  const warnings = touching.reduce((sum, p) => sum + p.warnings, 0);

  return (
    <>
      <div className="cmd-band" role="rowgroup">
        <span className="cmd-band-name">{unit.name}</span>
        <span className={`manager-analytics-status ${status.tone}`}>{status.label}</span>
        {warnings ? (
          <span className="cmd-band-warn"><AlertTriangle size={12} /> {warnings} אזהרות</span>
        ) : null}
        <button
          type="button"
          className="ghost-button cmd-band-chat"
          disabled={!unit.active}
          onClick={() => onChat(unit.id)}
          title={`שיחה עם הסוכן של ${unit.name}`}
        >
          <MessagesSquare size={14} /> סוכן
        </button>
        <button
          type="button"
          className="ghost-button cmd-band-enter"
          disabled={busy || !unit.active}
          onClick={() => onEnter(unit.id)}
        >
          <LogIn size={14} /> כניסה לניהול
        </button>
      </div>

      {shifts.length === 0 ? (
        <div className="cmd-band-empty">לא הוגדרו סוגי משמרות במשמרת הזו.</div>
      ) : (
        shifts.map((shift) => {
          const hours = unit.shifts.find((row) => row.name === shift);
          return (
            <div key={shift} className="cmd-row" role="row">
              <div className="board-rowhead" role="rowheader">
                <button
                  type="button"
                  className="cmd-shift-name board-rowhead-name"
                  onClick={() => onFocusShift(unit.id, shift)}
                  title="התמקדות בסוג המשמרת הזה"
                >
                  {shift}
                </button>
                {hours?.start_time ? (
                  <span className="board-rowhead-hours" dir="ltr">
                    {hours.start_time}–{hours.end_time}
                  </span>
                ) : null}
              </div>
              {days.map((day) => (
                <Cell key={day} unit={unit} shift={shift} day={day} today={today} dark={dark} hueOf={hueOf}
                  soldier={focus.soldier} hours={hours?.start_time ? `${hours.start_time}–${hours.end_time}` : ""} />
              ))}
            </div>
          );
        })
      )}
    </>
  );
}

function Cell({
  unit, shift, day, today, dark, hueOf, soldier, hours,
}: {
  unit: Unit;
  shift: string;
  day: string;
  today: string;
  dark: boolean;
  hueOf: (name: string) => number;
  soldier: string | null;
  hours: string;
}) {
  const cell = readCell(unit, shift, day);
  const base = ["board-cell", isWeekend(day) ? "is-weekend" : "", day === today ? "is-today" : ""];
  if (!cell) {
    return <div role="cell" className={[...base, "cmd-cell-unplanned"].join(" ")}>לא תוכנן</div>;
  }
  if (cell.seats === 0 && cell.names.length === 0) {
    return (
      <div role="cell" className={[...base, "is-absent"].join(" ")}>
        <span className="visually-hidden">אין משמרת</span>
      </div>
    );
  }
  const missing = cell.seats - cell.filled;
  return (
    <div role="cell" className={[...base, missing > 0 ? "is-short" : ""].filter(Boolean).join(" ")}>
      {cell.names.filter((name) => !soldier || soldier === `${unit.id}:${name}`).map((name) => (
        <div
          key={name}
          className={[
            "board-card cmd-card",
            cell.status === "draft" ? "is-draft" : "is-published",
            cell.shadows.has(name) ? "is-overlap" : "",
          ].filter(Boolean).join(" ")}
          // A נחפף/ת wears the board's one shared overlap colour, never a
          // person's hue, so they never read as a filled seat.
          style={cell.shadows.has(name) ? undefined : colorStyle(hueOf(`${unit.id}:${name}`), dark)}
          title={cell.shadows.has(name) ? "נחפף/ת — לא נספר/ת בתקן" : undefined}
        >
          <div className="board-card-main">
            <span className="board-card-name">{name}</span>
          </div>
          {hours || cell.shadows.has(name) ? (
            <div className="board-card-meta">
              {hours ? <span className="board-card-hours">{hours}</span> : null}
              {cell.shadows.has(name) ? <span className="board-card-overlap"><Users size={11} /> נחפף/ת</span> : null}
            </div>
          ) : null}
        </div>
      ))}
      {missing > 0 ? (
        <span className="board-gap"><AlertTriangle size={11} /> חסרים {missing}</span>
      ) : null}
    </div>
  );
}
