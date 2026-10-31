"use client";

import { Check, Clock, Trash2, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { buildPalette } from "@/components/Management/palette";
import type { Assignment, CardPerson, Closure, Constraint, Schedule } from "@/types";

import type { AgentTouch } from "./agentTouch";
import { buildScheduleIndex } from "./scheduleIndex";
import { useShiftOrder } from "./shiftOrder";
import type { BoardFilters } from "./useBoard";
import { useMoveMode } from "./useMoveMode";
import { BoardRow } from "./BoardRow";
import { DayHead } from "./DayHead";

/** The week as a board: days across, shifts down, cards inside.
 *
 *  The same grid draws a single day: `dates` is one column then, and every
 *  gesture below works unchanged, because a day is the week with six columns
 *  put away rather than a second board.
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
  dates,
  today,
  constraints,
  employees,
  roles,
  people,
  filters,
  dark,
  readOnly = false,
  touches,
  onDropCard,
  onDropEmployee,
  onRemoveCard,
  onOpenCard,
  onAddShift,
  onOpenDay,
  onBuildFrom,
  onClearDay,
  onOpenDate,
}: {
  schedule: Schedule | null;
  /** The columns to draw, in order: the seven days of a week, or one. */
  dates: string[];
  today: string;
  constraints: Constraint[];
  employees: string[];
  /** Employee name -> role, for the filter and the editor's picker. */
  roles: Record<string, string>;
  /** Employee name -> who they are, for the card's identity lines. */
  people: Record<string, CardPerson>;
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
  /** Assign a roster employee dropped from the team drawer. */
  onDropEmployee?: (input: {
    employee: string;
    shift_name: string;
    slot_date: string;
  }) => void;
  /** Remove one assignment by keyboard, touch, or dragging it to the trash. */
  onRemoveCard?: (assignment: Assignment) => void;
  onOpenCard?: (assignment: Assignment) => void;
  onAddShift?: (input: { shift_name: string; slot_date: string }) => void;
  onOpenDay?: (date: string) => void;
  /** Ask for a build starting on this day — until Saturday, or until a day
   *  the manager picks. Opens the build dialog and writes nothing itself.
   *  Withheld wherever clearing is, and for the same reasons. */
  onBuildFrom?: (date: string) => void;
  /** Clear one day's shifts. Withheld on a published board, where every
   *  write is refused, and while a build is running on this period. */
  onClearDay?: (date: string) => void;
  /** Show one column on its own. A change of view and nothing else — which
   *  is why it is offered on a published board too. */
  onOpenDate?: (date: string) => void;
}) {
  const [dragging, setDragging] = useState<Assignment | null>(null);
  const [over, setOver] = useState<string | null>(null);
  const [overTrash, setOverTrash] = useState(false);
  // The row being dragged to a new position, and the row it is currently
  // over. Separate from the card drag above because they are different acts
  // on different targets: one proposes a change to the week, the other only
  // changes the order it is read in.
  const [draggingShift, setDraggingShift] = useState<string | null>(null);
  const [overShift, setOverShift] = useState<string | null>(null);
  // The keyboard and touch path to the same move. Beside the drag rather
  // than replacing it: a mouse still drags, and both gestures end in the
  // same confirmation (D12).
  const move = useMoveMode();

  const hueOf = useMemo(() => buildPalette(employees), [employees]);

  // Bringing today into view on a board wider than the screen.
  //
  // The grid scrolls horizontally on a narrow viewport, and it opens at the
  // start of the week — which on a phone can leave today several columns off
  // screen, on the one week the manager is most likely looking at *because*
  // today is in it. Scrolled rather than laid out differently: the week stays
  // seven days, as the CSS note on the narrow breakpoint intends.
  const scroller = useRef<HTMLDivElement | null>(null);
  const todayColumn = useRef<HTMLDivElement | null>(null);
  const showsToday = dates.includes(today);
  useEffect(() => {
    if (!showsToday) return;
    const box = scroller.current;
    const column = todayColumn.current;
    if (!box || !column) return;
    // Nothing to do when the whole week already fits — scrolling a board
    // that is not scrollable just fights the browser for no gain.
    if (box.scrollWidth <= box.clientWidth) return;
    // `block: "nearest"` so bringing a column into view horizontally never
    // scrolls the page vertically as a side effect.
    column.scrollIntoView({
      inline: "center",
      block: "nearest",
      behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
        ? "auto"
        : "smooth",
    });
    // Re-run when the dates change: paging back to this week should land on
    // today again rather than wherever the previous week was scrolled to.
  }, [showsToday, dates]);

  // The week bucketed by cell, once. Every lookup below reads from this
  // instead of walking the assignment, slot and warning lists per cell.
  const index = useMemo(
    () => buildScheduleIndex(schedule, people),
    [schedule, people],
  );

  // Whose closure each date is, keyed for the column heads. Read off the
  // schedule rather than derived here: which group closes on 12/09 is
  // arithmetic the backend already did, and a browser-side cycle would be a
  // second answer to a question that must have exactly one (D3).
  const closures = useMemo(() => {
    const map = new Map<string, Closure>();
    for (const row of schedule?.closures ?? []) {
      if (row.groups.length) map.set(row.date, row);
    }
    return map;
  }, [schedule?.closures]);

  // When each shift starts, read off whichever slot in its row carries the
  // hours: a shift's times come from the vocabulary and hold all week, but a
  // shift that does not run on Sunday has no Sunday slot to read them from.
  const startTimes = useMemo(() => {
    const map: Record<string, string> = {};
    for (const slot of schedule?.slots ?? []) {
      if (slot.start_time && !map[slot.shift_name]) {
        map[slot.shift_name] = slot.start_time;
      }
    }
    return map;
  }, [schedule?.slots]);

  // Shift rows run by the clock, not by the order the slots happened to be
  // written in — a day happens morning, then noon, then evening, and a board
  // that opens with those rows shuffled has to be re-read every time. Still
  // not alphabetical, which would scramble the same sequence differently
  // (D9); and still the manager's to override, which is what `shiftOrder`
  // remembers.
  const order = useShiftOrder({ shifts: index.shifts, startTimes });
  const shiftFilter = filters.shift;
  const shifts = useMemo(
    () => order.shifts.filter((name) => !shiftFilter || name === shiftFilter),
    [order.shifts, shiftFilter],
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

  const removeCard = (card: Assignment) => {
    setDragging(null);
    setOver(null);
    setOverTrash(false);
    move.cancel();
    onRemoveCard?.(card);
  };

  return (
    <div
      className="board-grid-wrap"
      onDragEndCapture={() => setOverTrash(false)}
    >
      {dragging ? (
        <button
          type="button"
          className={`board-trash-target${overTrash ? " is-over" : ""}`}
          onDragOver={(event) => {
            if (!dragging) return;
            event.preventDefault();
            event.dataTransfer.dropEffect = "move";
            setOverTrash(true);
          }}
          onDragLeave={() => setOverTrash(false)}
          onDrop={(event) => {
            event.preventDefault();
            if (dragging) removeCard(dragging);
          }}
          onClick={() => {
            removeCard(dragging);
          }}
          aria-label={`הסרת השיבוץ של ${dragging.employee}`}
        >
          <Trash2 size={17} />
          שחרור כאן להסרת השיבוץ
        </button>
      ) : null}

      <div className="board-grid-scroll" ref={scroller} data-tour="grid">
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
              className="board-move-remove"
              onClick={() => removeCard(move.picked!)}
            >
              <Trash2 size={13} />
              הסרה
            </button>
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

      {/* A board no longer in clock order says so, and offers the clock
          back in one click. Shown only while the manager's own order
          actually differs from it: a row nudged and nudged back is not
          something to keep explaining. */}
      {order.custom ? (
        <div className="board-order-bar" role="status">
          <span className="board-order-bar-text">
            סדר המשמרות נקבע ידנית.
          </span>
          <button
            type="button"
            className="board-order-reset"
            onClick={order.reset}
            title="להחזיר את השורות לסדר לפי שעת ההתחלה"
          >
            <Clock size={13} />
            סידור לפי שעות
          </button>
        </div>
      ) : null}

      <div
        className={`board-grid${dates.length === 1 ? " is-day" : ""}`}
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
            closure={closures.get(date)}
            columnRef={date === today ? todayColumn : undefined}
            onOpenAgent={onOpenDay ? () => onOpenDay(date) : undefined}
            // Only on a day the period actually holds: a build aimed at a
            // column the period never opened has no rows to fill.
            onBuildFrom={
              onBuildFrom &&
              schedule &&
              date >= schedule.starts_on &&
              date <= schedule.ends_on
                ? () => onBuildFrom(date)
                : undefined
            }
            onClear={onClearDay ? () => onClearDay(date) : undefined}
            // Nothing to open when the day is already the only column.
            onOpen={
              onOpenDate && dates.length > 1
                ? () => onOpenDate(date)
                : undefined
            }
          />
        ))}

        {shifts.map((shift, row) => (
          <BoardRow
            key={shift}
            shift={shift}
            // Reordering is offered only when there is somewhere to reorder
            // to: a board filtered down to one shift row has no sequence to
            // change, and arrows that cannot move anything are noise.
            position={shifts.length > 1 ? { at: row, of: shifts.length } : null}
            order={order}
            draggingShift={draggingShift}
            setDraggingShift={setDraggingShift}
            overShift={overShift}
            setOverShift={setOverShift}
            dates={dates}
            today={today}
            schedule={schedule}
            index={index}
            cardsFor={cardsFor}
            constraints={constraints}
            roles={roles}
            people={people}
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
            onDropEmployee={onDropEmployee}
            onRemoveCard={removeCard}
            onOpenCard={onOpenCard}
            onAddShift={onAddShift}
          />
        ))}
        </div>
      </div>
    </div>
  );
}
