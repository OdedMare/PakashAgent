"use client";

import { Filter, UserMinus, X } from "lucide-react";

import { allShifts, NO_FOCUS, shiftsOf, soldiersOf, type Focus, type Unit } from "./figures";

/** Narrowing the combined board, in the משמרת board's own filter bar
 *  (`board-filters`): a משמרת, a shift type, one soldier, and "רק חוסרים".
 *  It hides; it never changes a row, and the tiles above keep counting
 *  every soldier of the משמרות and shift types chosen. */
export function CommanderFilters({
  units, focus, onChange,
}: {
  units: Unit[];
  focus: Focus;
  onChange: (next: Focus) => void;
}) {
  const unit = units.find((row) => row.id === focus.unit) ?? null;
  const shifts = unit ? shiftsOf(unit) : allShifts(units);
  const soldiers = soldiersOf(unit ? [unit] : units);
  const active = Boolean(focus.unit || focus.shift || focus.soldier || focus.gapsOnly);
  return (
    <div className="board-filters cmd-filters" role="group" aria-label="סינון לוח המכלול" data-tour="cmd-focus">
      <span className="board-filters-icon" aria-hidden="true"><Filter size={14} /></span>
      <Select
        label="משמרת"
        value={focus.unit ?? ""}
        allLabel="כל המשמרות"
        options={units.map((row) => ({ value: row.id, label: row.name }))}
        onChange={(value) => onChange({
          ...focus, unit: value || null,
          // A shift type or soldier the chosen משמרת does not have would
          // leave an empty board with no visible reason.
          shift: value && focus.shift && !shiftsOf(units.find((row) => row.id === value)!).includes(focus.shift)
            ? null : focus.shift,
          soldier: value && focus.soldier && !focus.soldier.startsWith(`${value}:`) ? null : focus.soldier,
        })}
      />
      <Select
        label="סוג משמרת"
        value={focus.shift ?? ""}
        allLabel="כל הסוגים"
        options={shifts.map((name) => ({ value: name, label: name }))}
        onChange={(value) => onChange({ ...focus, shift: value || null })}
      />
      <Select
        label="חייל"
        value={focus.soldier ?? ""}
        allLabel="כל החיילים"
        options={soldiers}
        onChange={(value) => onChange({ ...focus, soldier: value || null })}
      />
      <div className="board-filter-toggles">
        <button type="button" className={`board-toggle${focus.gapsOnly ? " is-on" : ""}`}
          aria-pressed={focus.gapsOnly} onClick={() => onChange({ ...focus, gapsOnly: !focus.gapsOnly })}>
          <span aria-hidden="true"><UserMinus size={13} /></span>
          רק חוסרים
        </button>
      </div>
      {active ? (
        <button type="button" className="board-filter-clear" onClick={() => onChange(NO_FOCUS)} title="ניקוי כל הסינונים">
          <X size={13} /> ניקוי
        </button>
      ) : null}
    </div>
  );
}

function Select({
  label, value, options, allLabel, onChange,
}: {
  label: string;
  value: string;
  options: { value: string; label: string }[];
  allLabel: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="board-filter-field">
      <span className="board-filter-label">{label}</span>
      <select className="board-filter-select" value={value} onChange={(event) => onChange(event.target.value)}>
        <option value="">{allLabel}</option>
        {options.map((option) => (
          <option key={option.value} value={option.value}>{option.label}</option>
        ))}
      </select>
    </label>
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
