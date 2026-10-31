"use client";

import { Search, X } from "lucide-react";

import type { PlacementCandidate } from "@/types";

const EXIT_PATTERN_FILTERS = [
  ["all", "הכול"],
  ["round", "סבב"],
  ["triplet", "תלתון"],
  ["quad", "רבעון"],
  ["quint", "חמישון"],
  ["hamshushim", "חמשוש"],
  ["shushim", "שוש"],
] as const;
type ExitPatternFilter = (typeof EXIT_PATTERN_FILTERS)[number][0];

const FLAG_FILTERS = [
  ["available", "פנויים בלבד"],
  ["closing", "בסגירה עכשיו"],
  ["manager", "מפקדים"],
  ["trainer", "מוסמכים לחפוף"],
  ["no_overlap", "בלי נחפפים"],
] as const;
type FlagFilter = (typeof FLAG_FILTERS)[number][0];

/** What the manual picker is narrowed to. Every field is "no filter" when
 *  empty, so the panel opens on everybody and a reset is one assignment. */
export interface CandidateFilter {
  query: string;
  exitPattern: ExitPatternFilter;
  /** A rotation label as the server words it ("סבב א", "חמשושים"). */
  rotation: string;
  /** A shift type the person must be allowed to work. */
  canWork: string;
  role: string;
  flags: FlagFilter[];
}

export const NO_FILTER: CandidateFilter = {
  query: "",
  exitPattern: "all",
  rotation: "",
  canWork: "",
  role: "",
  flags: [],
};

export function isFiltered(filter: CandidateFilter): boolean {
  return Boolean(
    filter.query.trim() || filter.exitPattern !== "all" || filter.rotation
    || filter.canWork || filter.role || filter.flags.length,
  );
}

/** Whether a candidate passes every filter the manager has set.
 *
 *  Pure, and run on what the server already sent: narrowing the list is a
 *  view over the placement check, not a second check. */
export function matchesFilter(
  candidate: PlacementCandidate,
  filter: CandidateFilter,
  roles: Record<string, string>,
): boolean {
  const query = filter.query.trim();
  if (query && !candidate.employee.includes(query)) return false;
  if (filter.exitPattern !== "all" && candidate.exit_pattern !== filter.exitPattern) return false;
  if (filter.rotation && candidate.rotation !== filter.rotation) return false;
  // An older server sends no list; the roster saying nothing is not "no".
  if (filter.canWork && candidate.eligible_shifts && !candidate.eligible_shifts.includes(filter.canWork)) return false;
  if (filter.role && roles[candidate.employee] !== filter.role) return false;
  return filter.flags.every((flag) => {
    if (flag === "available") return candidate.available;
    if (flag === "closing") return Boolean(candidate.closing);
    if (flag === "manager") return candidate.is_shift_manager;
    if (flag === "trainer") return candidate.can_train;
    return !candidate.is_overlap;
  });
}

/** The manual picker's filters: by name, rotation, the shift types a person
 *  may work, role, and a few yes/no qualities. */
export function CandidateFilters({
  candidates,
  shifts,
  roles,
  filter,
  shown,
  onChange,
}: {
  candidates: PlacementCandidate[];
  shifts: string[];
  roles: Record<string, string>;
  filter: CandidateFilter;
  shown: number;
  onChange: (filter: CandidateFilter) => void;
}) {
  const set = (patch: Partial<CandidateFilter>) => onChange({ ...filter, ...patch });

  // Only the groups the chosen exit pattern actually has, so picking "תלתון"
  // never leaves "סבב א" on offer.
  const rotations = distinct(candidates
    .filter((row) => filter.exitPattern === "all" || row.exit_pattern === filter.exitPattern)
    .map((row) => row.rotation ?? ""));
  const roleNames = distinct(candidates.map((row) => roles[row.employee] ?? ""));

  const toggle = (flag: FlagFilter) => set({
    flags: filter.flags.includes(flag)
      ? filter.flags.filter((item) => item !== flag)
      : [...filter.flags, flag],
  });

  return (
    <div className="board-candidate-filtering" role="group" aria-label="סינון החיילים">
      <label className="board-candidate-search">
        <Search size={14} aria-hidden="true" />
        <input
          type="search"
          value={filter.query}
          onChange={(event) => set({ query: event.target.value })}
          placeholder="חיפוש לפי שם"
          aria-label="חיפוש חייל/ת לפי שם"
        />
      </label>

      <div className="board-candidate-filters" aria-label="סינון לפי מבנה יציאות">
        {EXIT_PATTERN_FILTERS.map(([value, label]) => (
          <button
            type="button"
            key={value}
            className={filter.exitPattern === value ? "is-active" : undefined}
            aria-pressed={filter.exitPattern === value}
            onClick={() => set({ exitPattern: value, rotation: "" })}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="board-candidate-selects">
        {rotations.length ? (
          <label>
            <span>קבוצה בסבב</span>
            <select value={filter.rotation} onChange={(event) => set({ rotation: event.target.value })}>
              <option value="">כל הקבוצות</option>
              {rotations.map((name) => <option key={name} value={name}>{name}</option>)}
            </select>
          </label>
        ) : null}
        <label>
          <span>יכולים במשמרת</span>
          <select value={filter.canWork} onChange={(event) => set({ canWork: event.target.value })}>
            <option value="">כל סוגי המשמרות</option>
            {shifts.map((name) => <option key={name} value={name}>{name}</option>)}
          </select>
        </label>
        {roleNames.length ? (
          <label>
            <span>תפקיד</span>
            <select value={filter.role} onChange={(event) => set({ role: event.target.value })}>
              <option value="">כל התפקידים</option>
              {roleNames.map((name) => <option key={name} value={name}>{name}</option>)}
            </select>
          </label>
        ) : null}
      </div>

      <div className="board-candidate-filters" aria-label="סינון לפי תכונות">
        {FLAG_FILTERS.map(([value, label]) => (
          <button
            type="button"
            key={value}
            className={filter.flags.includes(value) ? "is-active" : undefined}
            aria-pressed={filter.flags.includes(value)}
            onClick={() => toggle(value)}
          >
            {label}
          </button>
        ))}
      </div>

      {isFiltered(filter) ? (
        <div className="board-candidate-filter-summary" role="status">
          <span>מוצגים {shown} מתוך {candidates.length}</span>
          <button type="button" className="ghost-button" onClick={() => onChange(NO_FILTER)}>
            <X size={13} />
            ניקוי הסינון
          </button>
        </div>
      ) : null}
    </div>
  );
}

function distinct(values: string[]): string[] {
  return Array.from(new Set(values.filter(Boolean))).sort((a, b) => a.localeCompare(b, "he"));
}
