"use client";

import { AlertTriangle, Filter, UserMinus, X } from "lucide-react";

import type { BoardFilters } from "./useBoard";

/** Narrowing the board down to what the manager is looking for.
 *
 *  Filtering **hides rows, it never changes them**. A person filtered out of
 *  view is still on the shift, still counted by the audit, and still in the
 *  coverage figures above — the summary deliberately reports the whole week
 *  rather than the filtered slice, because a manager who filtered to one
 *  employee and read "100% איוש" would have been told something false about
 *  their week.
 *
 *  The two focus toggles are separate from the dropdowns because they answer
 *  a different question. A dropdown asks "show me this"; "רק התנגשויות" asks
 *  "show me what needs me" — the thing a manager opens the board to find,
 *  and worth being one click rather than three selections.
 */
export function FilterBar({
  filters,
  employees,
  roles,
  shifts,
  active,
  onChange,
  onClear,
}: {
  filters: BoardFilters;
  employees: string[];
  roles: string[];
  shifts: string[];
  active: boolean;
  onChange: (next: Partial<BoardFilters>) => void;
  onClear: () => void;
}) {
  return (
    <div className="board-filters" role="group" aria-label="סינון הלוח">
      <span className="board-filters-icon" aria-hidden="true">
        <Filter size={14} />
      </span>

      <Select
        label="עובד"
        value={filters.employee}
        options={employees}
        allLabel="כל העובדים"
        onChange={(employee) => onChange({ employee })}
      />
      {/* Only when the workplace actually recorded roles. An empty dropdown
          is a promise the profile cannot keep, and the interview does not
          require the field. */}
      {roles.length ? (
        <Select
          label="תפקיד"
          value={filters.role}
          options={roles}
          allLabel="כל התפקידים"
          onChange={(role) => onChange({ role })}
        />
      ) : null}
      <Select
        label="משמרת"
        value={filters.shift}
        options={shifts}
        allLabel="כל המשמרות"
        onChange={(shift) => onChange({ shift })}
      />

      <div className="board-filter-toggles">
        <Toggle
          on={filters.conflictsOnly}
          onClick={() => onChange({ conflictsOnly: !filters.conflictsOnly })}
          icon={<AlertTriangle size={13} />}
          label="רק התנגשויות"
        />
        <Toggle
          on={filters.unassignedOnly}
          onClick={() => onChange({ unassignedOnly: !filters.unassignedOnly })}
          icon={<UserMinus size={13} />}
          label="רק חוסרים"
        />
      </div>

      {/* Present only when something is filtered. A permanent "clear"
          beside untouched filters invites a click that does nothing, and
          its appearing is itself the signal that the view is narrowed. */}
      {active ? (
        <button
          type="button"
          className="board-filter-clear"
          onClick={onClear}
          title="ניקוי כל הסינונים"
        >
          <X size={13} />
          ניקוי
        </button>
      ) : null}
    </div>
  );
}

function Select({
  label,
  value,
  options,
  allLabel,
  onChange,
}: {
  label: string;
  value: string;
  options: string[];
  allLabel: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="board-filter-field">
      <span className="board-filter-label">{label}</span>
      <select
        className="board-filter-select"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      >
        <option value="">{allLabel}</option>
        {options.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    </label>
  );
}

function Toggle({
  on,
  onClick,
  icon,
  label,
}: {
  on: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
}) {
  return (
    <button
      type="button"
      className={`board-toggle${on ? " is-on" : ""}`}
      onClick={onClick}
      aria-pressed={on}
    >
      <span aria-hidden="true">{icon}</span>
      {label}
    </button>
  );
}
