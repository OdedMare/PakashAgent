"use client";

import { AlertTriangle, LayoutGrid, LogIn, UserMinus, Users } from "lucide-react";

import { figuresOf, shiftsOf, type Unit } from "./figures";

/** "המשמרות": one card per משמרת of the מכלול with how its span on screen
 *  stands — coverage, open seats, warnings, whether it is published — and
 *  the two ways on: focus the board on it, or enter it to manage. */
export function UnitsView({
  units,
  days,
  busy,
  onEnter,
  onOpen,
}: {
  units: Unit[];
  days: string[];
  busy: boolean;
  onEnter: (id: string) => void;
  onOpen: (id: string) => void;
}) {
  if (units.length === 0) {
    return <p className="cmd-empty">עדיין לא שויכו משמרות למכלול. צוות משמרות זהב משייך אותן.</p>;
  }
  return (
    <ul className="cmd-units" aria-label="משמרות המכלול">
      {units.map((unit) => {
        const figures = figuresOf([unit], days, { unit: unit.id, shift: null });
        const percent = figures.seats ? Math.round((figures.assigned / figures.seats) * 100) : null;
        const status = figures.planned === 0
          ? { label: "לא תוכנן", tone: "" }
          : figures.published === 1
            ? { label: "פורסם", tone: "published" }
            : { label: "טיוטה", tone: "draft" };
        return (
          <li key={unit.id} className={`cmd-unit${unit.active ? "" : " is-off"}`}>
            <header>
              <div>
                <h2>{unit.name}</h2>
                <p>{unit.employees} חיילים · {shiftsOf(unit).length} סוגי משמרות</p>
              </div>
              <span className={`manager-analytics-status ${status.tone}`}>
                {unit.active ? status.label : "הושבתה"}
              </span>
            </header>
            <div className="cmd-unit-meter" aria-hidden="true">
              <span style={{ width: `${percent ?? 0}%` }} />
            </div>
            <dl className="cmd-unit-facts">
              <div><dt><Users size={13} /> איוש</dt><dd>{percent === null ? "—" : `${percent}%`}</dd></div>
              <div><dt><UserMinus size={13} /> מקומות פתוחים</dt><dd>{figures.open}</dd></div>
              <div><dt><AlertTriangle size={13} /> אזהרות</dt><dd>{figures.warnings}</dd></div>
            </dl>
            <div className="cmd-unit-shifts">
              {unit.shifts.map((shift) => (
                <span key={shift.name}>
                  {shift.name}
                  {shift.start_time ? <small dir="ltr">{shift.start_time}–{shift.end_time}</small> : null}
                </span>
              ))}
            </div>
            <footer>
              <button type="button" className="ghost-button" onClick={() => onOpen(unit.id)}>
                <LayoutGrid size={15} /> בלוח המכלול
              </button>
              <button type="button" className="primary-button" disabled={busy || !unit.active}
                onClick={() => onEnter(unit.id)}>
                <LogIn size={15} /> כניסה לניהול המשמרת
              </button>
            </footer>
          </li>
        );
      })}
    </ul>
  );
}
