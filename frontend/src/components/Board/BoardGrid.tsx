"use client";

import { AlertTriangle, Check, Moon, Plus, Sparkles, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { hebrewWeekday, isWeekend } from "@/components/Management/Calendar";
import { buildPalette } from "@/components/Management/palette";
import type {
  Assignment,
  Constraint,
  Schedule,
  ScheduleWarning,
  Slot,
} from "@/types";

import type { AgentTouch } from "./agentTouch";
import { touchKey } from "./agentTouch";
import type { ScheduleIndex } from "./scheduleIndex";
import { buildScheduleIndex } from "./scheduleIndex";
import { ShiftCard } from "./ShiftCard";
import type { BoardFilters } from "./useBoard";
import { weekDates } from "./useBoard";
import type { MoveMode } from "./useMoveMode";
import { useMoveMode } from "./useMoveMode";

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
  touches,
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
  /** Cells the agent is currently pointing at, keyed by `shift|date`. The
   *  board reads this and renders it; it never produces one, which is what
   *  keeps a highlight a description of the side column rather than a
   *  second channel the agent could act through. */
  touches?: Map<string, AgentTouch[]>;
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
  // The keyboard and touch path to the same move. Beside the drag rather
  // than replacing it: a mouse still drags, and both gestures end in the
  // same confirmation (D12).
  const move = useMoveMode();

  const dates = useMemo(() => weekDates(weekStart), [weekStart]);
  const hueOf = useMemo(() => buildPalette(employees), [employees]);

  // The week bucketed by cell, once. Every lookup below reads from this
  // instead of walking the assignment, slot and warning lists per cell.
  const index = useMemo(() => buildScheduleIndex(schedule), [schedule]);

  // Shift rows keep the vocabulary's own order — a workplace's shifts run
  // morning, then evening, then on-call, and alphabetising would scramble a
  // sequence that means something (D9).
  const shiftFilter = filters.shift;
  const shifts = useMemo(
    () => index.shifts.filter((name) => !shiftFilter || name === shiftFilter),
    [index, shiftFilter],
  );

  // Escape puts a picked card back down. Bound on the window because the
  // manager may have tabbed anywhere on the board between picking and
  // changing their mind, and a cancel that only works while one particular
  // card holds focus is one they cannot find.
  const picked = move.picked;
  const cancelMove = move.cancel;
  useEffect(() => {
    if (!picked) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") cancelMove();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [picked, cancelMove]);

  if (!schedule || !shifts.length) {
    return null;
  }

  /** Who is on this cell, after the filters.
   *
   *  The filters hide rows and change nothing: the returned cards are a
   *  view, and `slot.headcount` — what the cell is measured against — is
   *  read from the unfiltered index. A cell filtered down to one person must
   *  not start claiming it is short of the other two. */
  const cardsFor = (shift: string, date: string): Assignment[] => {
    const rows = index.assignments(shift, date);
    if (!filters.employee && !filters.role) return rows;
    return rows.filter((row) => {
      if (filters.employee && row.employee !== filters.employee) return false;
      if (filters.role && (roles[row.employee] ?? "") !== filters.role) {
        return false;
      }
      return true;
    });
  };

  /** Put the picked card down on this cell.
   *
   *  The same call a drop makes, so the confirmation, the check and the
   *  reason are identical whichever gesture got here. Landing it back where
   *  it started is a no-op rather than a change to account for — the same
   *  rule the drop path applies. */
  const placeOn = (shift: string, date: string) => {
    const card = move.picked;
    if (!card) return;
    move.cancel();
    if (card.shift === shift && card.date === date) return;
    onDropCard?.({ assignment: card, shift_name: shift, slot_date: date });
  };

  return (
    <div className="board-grid-scroll">
      {/* What a picked-up card is waiting for, said rather than left to be
          inferred from an outline. It carries no confirm: placing still
          opens the dialog that collects the reason (D12). */}
      {move.picked ? (
        <div className="board-move-bar" role="status">
          <Check size={14} />
          <span className="board-move-bar-text">
            {move.picked.employee} מוכן/ה למעבר — יש לבחור תא יעד.
          </span>
          <button
            type="button"
            className="board-move-cancel"
            onClick={move.cancel}
          >
            <X size={13} />
            ביטול
          </button>
        </div>
      ) : null}

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
            coverage={index.dayCoverage(date)}
          />
        ))}

        {shifts.map((shift) => (
          <BoardRow
            key={shift}
            shift={shift}
            dates={dates}
            today={today}
            schedule={schedule}
            index={index}
            cardsFor={cardsFor}
            constraints={constraints}
            roles={roles}
            hueOf={hueOf}
            dark={dark}
            filters={filters}
            readOnly={readOnly}
            touches={touches}
            dragging={dragging}
            over={over}
            setOver={setOver}
            setDragging={setDragging}
            move={move}
            onPlace={placeOn}
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
  coverage,
}: {
  date: string;
  isToday: boolean;
  /** Assigned and required for this day, counted once by the index. */
  coverage: { assigned: number; required: number };
}) {
  const { assigned, required } = coverage;

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
  index,
  cardsFor,
  constraints,
  roles,
  hueOf,
  dark,
  filters,
  readOnly,
  touches,
  dragging,
  over,
  setOver,
  setDragging,
  move,
  onPlace,
  onDropCard,
  onOpenCard,
  onAddShift,
}: {
  shift: string;
  dates: string[];
  today: string;
  schedule: Schedule;
  index: ScheduleIndex;
  cardsFor: (shift: string, date: string) => Assignment[];
  constraints: Constraint[];
  roles: Record<string, string>;
  hueOf: (name: string) => number;
  dark: boolean;
  filters: BoardFilters;
  readOnly: boolean;
  touches?: Map<string, AgentTouch[]>;
  dragging: Assignment | null;
  over: string | null;
  setOver: (key: string | null) => void;
  setDragging: (row: Assignment | null) => void;
  move: MoveMode;
  onPlace: (shift: string, date: string) => void;
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
        const slot = index.slot(shift, date);
        const key = touchKey(shift, date);
        const cards = cardsFor(shift, date);
        const warnings = index.warnings(shift, date);
        const short = slot ? cards.length < slot.headcount : false;
        // What the agent has said about this cell, if anything. A cell may
        // be touched by more than one source at once -- a simulation and
        // the answer that led to it -- and the strongest wins the outline,
        // which `collectTouches` has already ordered.
        const touched = touches?.get(key) ?? [];
        const touch = touched.length ? touched[touched.length - 1] : null;

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
          index.assignedCount(shift, date) < slot.headcount;
        if (filters.unassignedOnly && !shortOfHeadcount) {
          return <div key={key} className="board-cell is-filtered" />;
        }
        if (filters.conflictsOnly && !warnings.length) {
          return <div key={key} className="board-cell is-filtered" />;
        }

        // A cell the picked-up card could land on. Its own cell is not one:
        // putting a card back where it came from changes nothing, so it is
        // not offered as a destination.
        const isTarget =
          !readOnly &&
          Boolean(move.picked) &&
          !(move.picked?.shift === shift && move.picked?.date === date);

        return (
          <div
            key={key}
            className={[
              "board-cell",
              short ? "is-short" : "",
              over === key ? "is-over" : "",
              warnings.length ? "has-warning" : "",
              touch ? `is-touched is-touched-${touch.origin}` : "",
              isWeekend(date) ? "is-weekend" : "",
              date === today ? "is-today" : "",
              isTarget ? "is-target" : "",
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
                touched={
                  touched.find(
                    (item) =>
                      !item.employee || item.employee === row.employee,
                  )?.origin ?? null
                }
                dimmed={Boolean(dragging) && dragging?.id === row.id}
                picked={move.isPicked(row)}
                onDragStart={() => setDragging(row)}
                onDragEnd={() => {
                  setDragging(null);
                  setOver(null);
                }}
                onPick={readOnly ? undefined : () => move.pick(row)}
                onOpen={() => onOpenCard?.(row)}
              />
            ))}

            {/* Why this cell is lit, in words. The outline says the agent
                touched it; this says what it said — a highlight the manager
                cannot interpret is decoration. Nothing here is clickable:
                acting on it is still done in the side column, through the
                ordinary propose-then-confirm path (D8/D12). */}
            {touch ? (
              <span
                className={`board-touch is-${touch.origin}`}
                title={touched.map((row) => row.note).join("\n")}
              >
                <Sparkles size={10} />
                {touchLabel(touch.origin)}
              </span>
            ) : null}

            {short ? (
              <span className="board-gap">
                <AlertTriangle size={11} />
                חסרים {slot.headcount - cards.length}
              </span>
            ) : null}

            {/* The destination half of the keyboard and touch move. It is
                a real button covering the cell, so it is tabbable, has an
                accessible name, and answers to a tap — none of which the
                drop handler above does. It reports upward exactly as a drop
                does, so the confirmation and the reason are unchanged
                (D12). Rendered only while a card is actually picked up, so
                it never sits over an idle cell intercepting clicks. */}
            {isTarget ? (
              <button
                type="button"
                className="board-drop-target"
                onClick={() => onPlace(shift, date)}
                aria-label={`העברת ${move.picked?.employee} ל${shift} ב-${shortDate(date)}`}
                title="העברה לכאן"
              >
                <span className="board-drop-target-mark" aria-hidden="true">
                  <Check size={14} />
                </span>
              </button>
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
/** What the badge on a touched cell says.
 *
 *  Three words, because the badge sits inside a cell that already carries
 *  cards and a gap count. The full sentence is on the hover; this only has
 *  to say which of the three kinds of agent attention this is. */
function touchLabel(origin: AgentTouch["origin"]): string {
  if (origin === "proposal") return "הצעה";
  if (origin === "simulation") return "סימולציה";
  return "נבדק";
}

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
