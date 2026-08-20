"use client";

import { AlertTriangle, Clock, UserCheck, UserMinus } from "lucide-react";

import type { ScheduleWarning, ShiftStats } from "@/types";

/** The displayed week in four figures.
 *
 *  Every number here comes from `bl/audit.py` by way of the overview — none
 *  of it is recomputed in the browser. That is the same rule the stats panel
 *  and the employee's hours follow, and for the same reason: a figure
 *  derived from a second implementation would eventually disagree with the
 *  warning printed beside it, and the manager cannot tell by eye which one
 *  is lying.
 *
 *  **It reports; it does not grade.** There is no target, no threshold, and
 *  no colour that means "failing" — coverage at 80% is a fact about the week
 *  rather than a verdict on it (D3). The tiles turn amber only where a
 *  number is *actionable* (a gap to fill, a conflict to look at), which is a
 *  statement about what the manager can do, not about how they are doing.
 */
export function CoverageBar({
  stats,
  warnings,
  onFocusConflicts,
  onFocusUnassigned,
  conflictsActive = false,
  unassignedActive = false,
}: {
  stats: ShiftStats;
  warnings: ScheduleWarning[];
  onFocusConflicts?: () => void;
  onFocusUnassigned?: () => void;
  conflictsActive?: boolean;
  unassignedActive?: boolean;
}) {
  const coverage = stats.coverage;
  // Notices are real findings but they are not things gone wrong —
  // overstaffing costs money and breaks nothing. Counting them into a
  // "conflicts" tile would make the number the manager reacts to include
  // things needing no reaction.
  const conflicts = warnings.filter(
    (row) => row.severity === "warning",
  ).length;

  return (
    <div className="board-coverage" role="group" aria-label="סיכום השבוע">
      <Tile
        icon={<UserCheck size={15} />}
        label="איוש"
        value={`${Math.round(coverage.percent)}%`}
        detail={`${coverage.assigned} מתוך ${coverage.required} מקומות`}
        tone={coverage.percent >= 100 ? "good" : "plain"}
      />
      <Tile
        icon={<UserMinus size={15} />}
        label="משמרות פתוחות"
        value={`${coverage.unfilled_slots}`}
        detail={coverage.unfilled_slots ? "לחיצה לסינון" : "אין חוסרים"}
        tone={coverage.unfilled_slots ? "attention" : "good"}
        onClick={coverage.unfilled_slots ? onFocusUnassigned : undefined}
        active={unassignedActive}
      />
      <Tile
        icon={<AlertTriangle size={15} />}
        label="התנגשויות"
        value={`${conflicts}`}
        detail={conflicts ? "לחיצה לסינון" : "לא נמצאו"}
        tone={conflicts ? "attention" : "good"}
        onClick={conflicts ? onFocusConflicts : undefined}
        active={conflictsActive}
      />
      <Tile
        icon={<Clock size={15} />}
        label="שעות משובצות"
        value={prettyHours(stats.total_hours)}
        detail={`${stats.people_working} עובדים · ${stats.total_shifts} משמרות`}
        tone="plain"
      />
    </div>
  );
}

/** One figure.
 *
 *  Rendered as a `button` only when it does something. A div that looks
 *  clickable and is not is worse than a plain figure, and a button that
 *  does nothing is unreachable noise for a keyboard. */
function Tile({
  icon,
  label,
  value,
  detail,
  tone,
  onClick,
  active = false,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  detail: string;
  tone: "plain" | "good" | "attention";
  onClick?: () => void;
  active?: boolean;
}) {
  const className = [
    "board-tile",
    `is-${tone}`,
    onClick ? "is-clickable" : "",
    active ? "is-active" : "",
  ]
    .filter(Boolean)
    .join(" ");

  const body = (
    <>
      <span className="board-tile-head">
        <span className="board-tile-icon" aria-hidden="true">
          {icon}
        </span>
        {label}
      </span>
      <strong className="board-tile-value">{value}</strong>
      <span className="board-tile-detail">{detail}</span>
    </>
  );

  if (!onClick) {
    return <div className={className}>{body}</div>;
  }
  return (
    <button
      type="button"
      className={className}
      onClick={onClick}
      aria-pressed={active}
    >
      {body}
    </button>
  );
}

/** Hours without a pointless decimal. 40.0 reads as 40, 37.5 stays 37.5. */
function prettyHours(hours: number): string {
  return Number.isFinite(hours) ? `${Math.round(hours * 10) / 10}` : "0";
}
