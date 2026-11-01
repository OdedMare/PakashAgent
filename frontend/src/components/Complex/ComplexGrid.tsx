"use client";

import { AlertTriangle, LogIn } from "lucide-react";
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
}) {
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
            </div>
          ))}

          {units.map((unit) => (
            <UnitBand
              key={unit.id}
              unit={unit}
              days={days}
              today={today}
              focus={focus}
              dark={dark}
              hueOf={hueOf}
              busy={busy}
              onFocusShift={onFocusShift}
              onEnter={onEnter}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

function UnitBand({
  unit, days, today, focus, dark, hueOf, busy, onFocusShift, onEnter,
}: {
  unit: Unit;
  days: string[];
  today: string;
  focus: Focus;
  dark: boolean;
  hueOf: (name: string) => number;
  busy: boolean;
  onFocusShift: (unit: string, shift: string) => void;
  onEnter: (unit: string) => void;
}) {
  const shifts = shiftsOf(unit).filter((name) => !focus.shift || name === focus.shift);
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
                <Cell key={day} unit={unit} shift={shift} day={day} today={today} dark={dark} hueOf={hueOf} />
              ))}
            </div>
          );
        })
      )}
    </>
  );
}

function Cell({
  unit, shift, day, today, dark, hueOf,
}: {
  unit: Unit;
  shift: string;
  day: string;
  today: string;
  dark: boolean;
  hueOf: (name: string) => number;
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
  const missing = cell.seats - cell.names.length;
  return (
    <div role="cell" className={[...base, missing > 0 ? "is-short" : ""].filter(Boolean).join(" ")}>
      {cell.names.map((name) => (
        <div
          key={name}
          className={`board-card cmd-card ${cell.status === "draft" ? "is-draft" : "is-published"}`}
          style={colorStyle(hueOf(`${unit.id}:${name}`), dark)}
        >
          <div className="board-card-main">
            <span className="board-card-name">{name}</span>
          </div>
        </div>
      ))}
      {missing > 0 ? (
        <span className="board-gap"><AlertTriangle size={11} /> חסרים {missing}</span>
      ) : null}
    </div>
  );
}
