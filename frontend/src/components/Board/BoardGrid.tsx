"use client";

import { AlertTriangle, Moon, Plus } from "lucide-react";
import { useMemo, useState } from "react";

import { hebrewWeekday, isWeekend } from "@/components/Management/Calendar";
import { buildPalette } from "@/components/Management/palette";
import type {
  Assignment,
  Constraint,
  Schedule,
  ScheduleWarning,
  Slot,
} from "@/types";

import { ShiftCard } from "./ShiftCard";
import type { BoardFilters } from "./useBoard";
import { weekDates } from "./useBoard";

/** The week as a board: days across, shifts down, cards inside.
 *
 *  Days are the primary timeline because that is how the manager thinks —
 *  "who is on Tuesday" is the question, and the existing product direction
 *  (`Calendar.tsx`, `bl/export.py`, the real source files in
 *  FILE_FORMATS.md) has always laid a week out this way. An
 *  employees-as-rows board would be a second, disagreeing model of the same
 *  week and would not match the file a schedule leaves as.
 *
 *  What is new here is not the axes but the *density*: a card carries the
 *  person, their role, the shift and its hours, its status and its warning
 *  state, so the week is readable without hovering anything. The old grid
 *  put the reason behind a `title` and the role nowhere.
 *
 *  **Drag proposes; it does not write** ([D12](../../../docs/DECISIONS.md#d12--dragging-a-shift-is-a-proposal-not-an-edit)).
 *  This component reports a drop upward and changes nothing itself. What it
 *  adds over the old calendar is that the drop is *validated first* — the
 *  board asks `bl/placement.py` what the move would cost and the dialog
 *  shows it, so an invalid move is explained before the manager commits
 *  rather than warned about after. That check contains no model call, so it
 *  works with the agent unavailable.
 */
export function BoardGrid({
  schedule,
  weekStart,
  today,
  constraints,
  employees,
  roles,
  filters,
  dark,
  readOnly = false,
  onDropCard,
  onOpenCard,
  onAddShift,
}: {
  schedule: Schedule | null;
  weekStart: string;
  today: string;
  constraints: Constraint[];
  employees: string[];
  /** Employee name -> role, for the card's second line. */
  roles: Record<string, string>;
  filters: BoardFilters;
  dark: boolean;
  readOnly?: boolean;
  onDropCard?: (move: {
    assignment: Assignment;
    shift_name: string;
    slot_date: string;
  }) => void;
  onOpenCard?: (assignment: Assignment) => void;
  onAddShift?: (input: { shift_name: string; slot_date: string }) => void;
}) {
  const [dragging, setDragging] = useState<Assignment | null>(null);
  const [over, setOver] = useState<string | null>(null);

  const dates = useMemo(() => weekDates(weekStart), [weekStart]);
  const hueOf = useMemo(() => buildPalette(employees), [employees]);

  // Shift rows keep the vocabulary's own order — a workplace's shifts run
  // morning, then evening, then on-call, and alphabetising would scramble a
  // sequence that means something (D9).
  const shifts = useMemo(() => {
    const seen = new Set<string>();
    const ordered: string[] = [];
    for (const slot of schedule?.slots ?? []) {
      if (seen.has(slot.shift_name)) continue;
      seen.add(slot.shift_name);
      ordered.push(slot.shift_name);
    }
    return ordered.filter(
      (name) => !filters.shift || name === filters.shift,
    );
  }, [schedule, filters.shift]);

  if (!schedule || !shifts.length) {
    return null;
  }

  const slotFor = (shift: string, date: string): Slot | undefined =>
    schedule.slots.find(
      (slot) => slot.shift_name === shift && slot.slot_date === date,
    );

  const warningsFor = (shift: string, date: string): ScheduleWarning[] =>
    schedule.warnings.filter(
      (row) => row.date === date && (row.shift === shift || row.shift === ""),
    );

  /** Who is on this cell, after the filters.
   *
   *  The filters hide rows and change nothing: the returned cards are a
   *  view, and `slot.headcount` — what the cell is measured against — is
   *  read from the unfiltered grid. A cell filtered down to one person must
   *  not start claiming it is short of the other two. */
  const cardsFor = (shift: string, date: string): Assignment[] =>
    schedule.assignments.filter((row) => {
      if (row.shift !== shift || row.date !== date) return false;
      if (filters.employee && row.employee !== filters.employee) return false;
      if (filters.role && (roles[row.employee] ?? "") !== filters.role) {
        return false;
      }
      return true;
    });

  return (
    <div className="board-grid-scroll">
      <div
        className="board-grid"
        dir="rtl"
        style={{ "--board-days": dates.length } as React.CSSProperties}
      >
        {/* Header row: the corner, then a column head per day. */}
        <div className="board-corner" aria-hidden="true">
          משמרת
        </div>
        {dates.map((date) => (
          <DayHead
            key={date}
            date={date}
            isToday={date === today}
            schedule={schedule}
          />
        ))}

        {shifts.map((shift) => (
          <BoardRow
            key={shift}
            shift={shift}
            dates={dates}
            today={today}
            schedule={schedule}
            slotFor={slotFor}
            cardsFor={cardsFor}
            warningsFor={warningsFor}
            constraints={constraints}
            roles={roles}
            hueOf={hueOf}
            dark={dark}
            filters={filters}
            readOnly={readOnly}
            dragging={dragging}
            over={over}
            setOver={setOver}
            setDragging={setDragging}
            onDropCard={onDropCard}
            onOpenCard={onOpenCard}
            onAddShift={onAddShift}
          />
        ))}
      </div>
    </div>
  );
}

/** One day's column head.
 *
 *  Today is marked here rather than only on the cells beneath it, because
 *  the head is where the eye lands first when the question is "where am I".
 *  The per-day coverage line under the date is what makes the header worth
 *  its height: it answers "is this day staffed" without reading the column. */
function DayHead({
  date,
  isToday,
  schedule,
}: {
  date: string;
  isToday: boolean;
  schedule: Schedule;
}) {
  const slots = schedule.slots.filter((slot) => slot.slot_date === date);
  const required = slots.reduce(
    (total, slot) => total + (slot.headcount || 0),
    0,
  );
  const assigned = schedule.assignments.filter(
    (row) => row.date === date,
  ).length;

  return (
    <div
      className={[
        "board-dayhead",
        isToday ? "is-today" : "",
        isWeekend(date) ? "is-weekend" : "",
      ]
        .filter(Boolean)
        .join(" ")}
    >
      <span className="board-dayhead-weekday">{hebrewWeekday(date)}</span>
      <span className="board-dayhead-date">{shortDate(date)}</span>
      {required ? (
        <span
          className={`board-dayhead-coverage${
            assigned < required ? " is-short" : ""
          }`}
          title={`${assigned} מתוך ${required} מקומות מאוישים`}
        >
          {assigned}/{required}
        </span>
      ) : (
        <span className="board-dayhead-coverage is-empty">—</span>
      )}
      {isToday ? <span className="board-dayhead-pill">היום</span> : null}
    </div>
  );
}

/** One shift's row across the week. */
function BoardRow({
  shift,
  dates,
  today,
  schedule,
  slotFor,
  cardsFor,
  warningsFor,
  constraints,
  roles,
  hueOf,
  dark,
  filters,
  readOnly,
  dragging,
  over,
  setOver,
  setDragging,
  onDropCard,
  onOpenCard,
  onAddShift,
}: {
  shift: string;
  dates: string[];
  today: string;
  schedule: Schedule;
  slotFor: (shift: string, date: string) => Slot | undefined;
  cardsFor: (shift: string, date: string) => Assignment[];
  warningsFor: (shift: string, date: string) => ScheduleWarning[];
  constraints: Constraint[];
  roles: Record<string, string>;
  hueOf: (name: string) => number;
  dark: boolean;
  filters: BoardFilters;
  readOnly: boolean;
  dragging: Assignment | null;
  over: string | null;
  setOver: (key: string | null) => void;
  setDragging: (row: Assignment | null) => void;
  onDropCard?: (move: {
    assignment: Assignment;
    shift_name: string;
    slot_date: string;
  }) => void;
  onOpenCard?: (assignment: Assignment) => void;
  onAddShift?: (input: { shift_name: string; slot_date: string }) => void;
}) {
  // The hours are read off whichever slot in the row carries them: a shift's
  // times come from the vocabulary and are the same all week, but a slot
  // that does not run on Sunday has none to read.
  const withTimes = schedule.slots.find(
    (slot) => slot.shift_name === shift && slot.start_time,
  );
  const onCall = schedule.slots.some(
    (slot) => slot.shift_name === shift && slot.is_on_call,
  );

  return (
    <>
      <div className="board-rowhead">
        <span className="board-rowhead-name">
          {shift}
          {onCall ? (
            <span className="board-rowhead-oncall" title="כוננות">
              <Moon size={12} />
            </span>
          ) : null}
        </span>
        {withTimes?.start_time ? (
          <span className="board-rowhead-hours">
            {withTimes.start_time}–{withTimes.end_time}
          </span>
        ) : null}
      </div>

      {dates.map((date) => {
        const slot = slotFor(shift, date);
        const key = `${shift}|${date}`;
        const cards = cardsFor(shift, date);
        const warnings = warningsFor(shift, date);
        const short = slot ? cards.length < slot.headcount : false;

        // The shift does not run this day. Not a gap — nothing is missing.
        if (!slot) {
          return (
            <div key={key} className="board-cell is-absent">
              <span className="visually-hidden">אין משמרת</span>
            </div>
          );
        }

        // Focus filters hide whole cells rather than dimming them: "רק
        // חוסרים" exists to make a short week scannable, and a board still
        // showing every full cell at 40% opacity is not scannable.
        const shortOfHeadcount =
          schedule.assignments.filter(
            (row) => row.shift === shift && row.date === date,
          ).length < slot.headcount;
        if (filters.unassignedOnly && !shortOfHeadcount) {
          return <div key={key} className="board-cell is-filtered" />;
        }
        if (filters.conflictsOnly && !warnings.length) {
          return <div key={key} className="board-cell is-filtered" />;
        }

        return (
          <div
            key={key}
            className={[
              "board-cell",
              short ? "is-short" : "",
              over === key ? "is-over" : "",
              warnings.length ? "has-warning" : "",
              isWeekend(date) ? "is-weekend" : "",
              date === today ? "is-today" : "",
            ]
              .filter(Boolean)
              .join(" ")}
            onDragOver={(event) => {
              if (readOnly || !dragging) return;
              // Preventing default is what marks a valid drop target;
              // without it the browser refuses the drop entirely.
              event.preventDefault();
              event.dataTransfer.dropEffect = "move";
              setOver(key);
            }}
            onDragLeave={() => setOver(over === key ? null : over)}
            onDrop={(event) => {
              event.preventDefault();
              setOver(null);
              if (readOnly || !dragging) return;
              // Dropping where it came from is a no-op, not a change worth
              // asking the manager to account for.
              if (dragging.shift === shift && dragging.date === date) {
                setDragging(null);
                return;
              }
              onDropCard?.({
                assignment: dragging,
                shift_name: shift,
                slot_date: date,
              });
              setDragging(null);
            }}
          >
            {cards.map((row) => (
              <ShiftCard
                key={row.id}
                assignment={row}
                role={roles[row.employee] ?? ""}
                slot={slot}
                hue={hueOf(row.employee)}
                dark={dark}
                status={schedule.status}
                blocked={isBlocked(constraints, row.employee, date, shift)}
                warnings={warnings.filter(
                  (warning) =>
                    !warning.employee || warning.employee === row.employee,
                )}
                draggable={!readOnly}
                dimmed={Boolean(dragging) && dragging?.id === row.id}
                onDragStart={() => setDragging(row)}
                onDragEnd={() => {
                  setDragging(null);
                  setOver(null);
                }}
                onOpen={() => onOpenCard?.(row)}
              />
            ))}

            {short ? (
              <span className="board-gap">
                <AlertTriangle size={11} />
                חסרים {slot.headcount - cards.length}
              </span>
            ) : null}

            {/* Creating a shift by clicking an empty cell. The picker and
                the write live in the editor this opens — the cell only says
                where. */}
            {!readOnly && onAddShift ? (
              <button
                type="button"
                className="board-add"
                onClick={() =>
                  onAddShift({ shift_name: shift, slot_date: date })
                }
                aria-label={`הוספת שיבוץ ל${shift} ב-${shortDate(date)}`}
                title="הוספת שיבוץ"
              >
                <Plus size={13} />
              </button>
            ) : null}
          </div>
        );
      })}
    </>
  );
}

/** Whether a recorded constraint contradicts this cell.
 *
 *  An empty `shift_name` covers the whole day — the convention the interview
 *  collects and `audit.py` reads. */
function isBlocked(
  constraints: Constraint[],
  employee: string,
  date: string,
  shift: string,
): boolean {
  return constraints.some(
    (row) =>
      !row.available &&
      row.employee === employee &&
      row.constraint_date === date &&
      (row.shift_name === "" || row.shift_name === shift),
  );
}

function shortDate(iso: string): string {
  const date = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(date.getTime())) return iso;
  return `${date.getDate()}.${date.getMonth() + 1}`;
}
