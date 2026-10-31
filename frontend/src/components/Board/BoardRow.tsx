"use client";

import {
  AlertTriangle,
  Check,
  ChevronDown,
  ChevronUp,
  GripVertical,
  Moon,
  Plus,
  Sparkles,
} from "lucide-react";

import { isWeekend } from "@/components/Management/Calendar";
import { constraintBlocksSlot } from "@/lib/constraints";
import type { Assignment, CardPerson, Constraint, Schedule } from "@/types";
import { shortDate } from "@/components/DateInput";

import type { AgentTouch } from "./agentTouch";
import { touchKey } from "./agentTouch";
import { EMPLOYEE_DRAG_TYPE } from "./dragData";
import { EMPTY_PERSON } from "./person";
import type { ScheduleIndex } from "./scheduleIndex";
import type { ShiftOrder } from "./shiftOrder";
import { SHIFT_DRAG_TYPE } from "./shiftOrder";
import { ShiftCard } from "./ShiftCard";
import type { BoardFilters } from "./useBoard";
import type { MoveMode } from "./useMoveMode";

/** Audit codes about how many are on a cell, which its badge already counts. */
const HEADCOUNT_CODES = new Set(["unfilled", "overstaffed"]);

/** One shift's row across the week. */
export function BoardRow({
  shift,
  position,
  order,
  draggingShift,
  setDraggingShift,
  overShift,
  setOverShift,
  dates,
  today,
  schedule,
  index,
  cardsFor,
  constraints,
  roles,
  people,
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
  onDropEmployee,
  onRemoveCard,
  onOpenCard,
  onAddShift,
}: {
  shift: string;
  /** Where this row sits and how many there are, or null when the board is
   *  showing too few rows for an order to exist. */
  position: { at: number; of: number } | null;
  order: ShiftOrder;
  draggingShift: string | null;
  setDraggingShift: (shift: string | null) => void;
  overShift: string | null;
  setOverShift: (shift: string | null) => void;
  dates: string[];
  today: string;
  schedule: Schedule;
  index: ScheduleIndex;
  cardsFor: (shift: string, date: string) => Assignment[];
  constraints: Constraint[];
  roles: Record<string, string>;
  people: Record<string, CardPerson>;
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
  onDropEmployee?: (input: {
    employee: string;
    shift_name: string;
    slot_date: string;
  }) => void;
  onRemoveCard: (assignment: Assignment) => void;
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

  const reorderable = position !== null;

  return (
    <>
      {/* The row head is the handle. Dragging it reorders the board and
          writes nothing — no assignment moves, so there is no reason to
          collect and no dialog to open, which is why this gesture looks
          like the card drag but ends nowhere near it (D12). It stays
          available on a published board for the same reason: the week is
          read-only, the order it is read in is not. */}
      <div
        className={[
          "board-rowhead",
          reorderable ? "is-reorderable" : "",
          draggingShift === shift ? "is-dragging" : "",
          overShift === shift && draggingShift !== shift ? "is-over" : "",
        ]
          .filter(Boolean)
          .join(" ")}
        draggable={reorderable}
        onDragStart={(event) => {
          if (!reorderable) return;
          event.dataTransfer.setData(SHIFT_DRAG_TYPE, shift);
          event.dataTransfer.effectAllowed = "move";
          setDraggingShift(shift);
        }}
        onDragEnd={() => {
          setDraggingShift(null);
          setOverShift(null);
        }}
        onDragOver={(event) => {
          // Only a row drag lands here. A card or a roster name dragged
          // over the head is not a placement — there is no cell under it —
          // so it is left un-droppable rather than silently reordering.
          if (!event.dataTransfer.types.includes(SHIFT_DRAG_TYPE)) return;
          event.preventDefault();
          event.dataTransfer.dropEffect = "move";
          setOverShift(shift);
        }}
        onDragLeave={() => {
          if (overShift === shift) setOverShift(null);
        }}
        onDrop={(event) => {
          if (!event.dataTransfer.types.includes(SHIFT_DRAG_TYPE)) return;
          event.preventDefault();
          const moved = event.dataTransfer.getData(SHIFT_DRAG_TYPE).trim();
          setDraggingShift(null);
          setOverShift(null);
          if (moved && moved !== shift) order.moveTo(moved, shift);
        }}
      >
        <span className="board-rowhead-name">
          {reorderable ? (
            <span className="board-rowhead-grip" aria-hidden="true">
              <GripVertical size={12} />
            </span>
          ) : null}
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

        {/* The same reorder, without a mouse. HTML5 drag fires on neither
            touch nor the keyboard, and the row order is exactly the kind of
            thing a manager fixes once on a phone — so the arrows are the
            reachable path, not a fallback. */}
        {position ? (
          <span className="board-rowhead-move">
            <button
              type="button"
              onClick={() => order.nudge(shift, -1)}
              disabled={position.at === 0}
              aria-label={`הזזת ${shift} שורה למעלה`}
              title="שורה למעלה"
            >
              <ChevronUp size={13} />
            </button>
            <button
              type="button"
              onClick={() => order.nudge(shift, 1)}
              disabled={position.at === position.of - 1}
              aria-label={`הזזת ${shift} שורה למטה`}
              title="שורה למטה"
            >
              <ChevronDown size={13} />
            </button>
          </span>
        ) : null}
      </div>

      {dates.map((date) => {
        const slot = index.slot(shift, date);
        const key = touchKey(shift, date);
        const cards = cardsFor(shift, date);
        const warnings = index.warnings(shift, date);
        // Measured in filled seats, never in rendered cards. Two separate
        // reasons the two differ, and each on its own produced a badge that
        // lied: the cards are a *filtered view*, so a role filter made every
        // full cell claim it was short of the people it had just hidden; and
        // somebody shadowing the shift is a card who is not a seat, so a cell
        // with its trainee on it read as covered while the audit underneath
        // still called it short.
        const filled = slot ? index.filledSeats(shift, date) : 0;
        const missing = slot ? slot.headcount - filled : 0;
        const short = missing > 0;
        const surplus = missing < 0 ? -missing : 0;
        // A headcount finding belongs to the cell, not to the people on it:
        // the badge below already says how many are missing or extra, so it
        // must not paint every card in the cell as a warning too. Cards get
        // only what names them; what names nobody stays on the cell.
        const cellWarnings = warnings.filter(
          (warning) =>
            !warning.employee && !HEADCOUNT_CODES.has(warning.code),
        );
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
        // showing every full cell at 40% opacity is not scannable. `short` is
        // the same seat count the badge uses, so the filter keeps exactly the
        // cells that are wearing one.
        if (filters.unassignedOnly && !short) {
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
              cellWarnings.length ? "has-warning" : "",
              touch ? `is-touched is-touched-${touch.origin}` : "",
              isWeekend(date) ? "is-weekend" : "",
              date === today ? "is-today" : "",
              isTarget ? "is-target" : "",
            ]
              .filter(Boolean)
              .join(" ")}
            onDragOver={(event) => {
              const rosterDrag = event.dataTransfer.types.includes(
                EMPLOYEE_DRAG_TYPE,
              );
              if (readOnly || (!dragging && !rosterDrag)) return;
              // Preventing default is what marks a valid drop target;
              // without it the browser refuses the drop entirely.
              event.preventDefault();
              event.dataTransfer.dropEffect = rosterDrag ? "copy" : "move";
              setOver(key);
            }}
            onDragLeave={() => setOver(over === key ? null : over)}
            onDrop={(event) => {
              event.preventDefault();
              setOver(null);
              if (readOnly) return;
              const employee = event.dataTransfer
                .getData(EMPLOYEE_DRAG_TYPE)
                .trim();
              if (employee) {
                onDropEmployee?.({
                  employee,
                  shift_name: shift,
                  slot_date: date,
                });
                return;
              }
              if (!dragging) return;
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
                person={people[row.employee] ?? EMPTY_PERSON}
                slot={slot}
                hue={hueOf(row.employee)}
                dark={dark}
                status={schedule.status}
                blocked={constraintBlocksSlot(
                  constraints, row.employee, date, slot,
                )}
                warnings={warnings.filter(
                  (warning) => warning.employee === row.employee,
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
                onRemove={readOnly ? undefined : () => onRemoveCard(row)}
                onOpen={readOnly ? undefined : () => onOpenCard?.(row)}
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
              <span
                className="board-gap"
                title={cellWarnings.map((w) => w.message).join("\n") || undefined}
              >
                <AlertTriangle size={11} />
                חסרים {missing}
              </span>
            ) : surplus ? (
              <span className="board-gap is-surplus">
                עודפים {surplus}
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
 *  An empty `shift_name` covers the whole day — the convention setup
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
