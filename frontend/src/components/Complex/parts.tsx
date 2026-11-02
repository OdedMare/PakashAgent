"use client";

import { shiftsOf, type Focus, type Unit } from "./figures";

/** Narrowing the board: a משמרת, then one of its shift types. The board's
 *  own segmented control, changing only what is shown. */
export function FocusBar({
  units, focus, onUnit, onShift,
}: {
  units: Unit[];
  focus: Focus;
  onUnit: (id: string | null) => void;
  onShift: (shift: string | null) => void;
}) {
  const unit = units.find((row) => row.id === focus.unit) ?? null;
  return (
    <div className="cmd-focus" data-tour="cmd-focus">
      <div className="board-views" role="group" aria-label="משמרת">
        <button type="button" className={`board-view${focus.unit === null ? " is-on" : ""}`}
          aria-pressed={focus.unit === null} onClick={() => onUnit(null)}>
          כל המשמרות
        </button>
        {units.map((row) => (
          <button key={row.id} type="button" className={`board-view${focus.unit === row.id ? " is-on" : ""}`}
            aria-pressed={focus.unit === row.id} onClick={() => onUnit(row.id)}>
            {row.name}
          </button>
        ))}
      </div>
      {unit ? (
        <div className="board-views" role="group" aria-label={`סוגי משמרות ב${unit.name}`}>
          <button type="button" className={`board-view${focus.shift === null ? " is-on" : ""}`}
            aria-pressed={focus.shift === null} onClick={() => onShift(null)}>
            כל סוגי המשמרות
          </button>
          {shiftsOf(unit).map((shift) => (
            <button key={shift} type="button" className={`board-view${focus.shift === shift ? " is-on" : ""}`}
              aria-pressed={focus.shift === shift} onClick={() => onShift(shift)}>
              {shift}
            </button>
          ))}
        </div>
      ) : (
        <span className="cmd-hint">בחרו משמרת כדי להתמקד גם בסוג משמרת מסוים.</span>
      )}
    </div>
  );
}

export function Tile({
  icon, label, value, detail, tone,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  detail: string;
  tone: "plain" | "good" | "attention";
}) {
  return (
    <div className={`board-tile is-${tone}`}>
      <span className="board-tile-head">
        <span className="board-tile-icon" aria-hidden="true">{icon}</span>
        {label}
      </span>
      <strong className="board-tile-value">{value}</strong>
      <span className="board-tile-detail">{detail}</span>
    </div>
  );
}
