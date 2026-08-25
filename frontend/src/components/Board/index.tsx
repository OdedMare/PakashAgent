"use client";

import {
  AlertTriangle,
  Download,
  Eye,
  EyeOff,
  LoaderCircle,
  LockKeyhole,
  PencilLine,
  RefreshCw,
  Sparkles,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type {
  AgentAnswer,
  Assignment,
  Constraint,
  ManagementOverview,
  PlacementCheck,
  Proposal,
  RequiredAssignment,
  Schedule,
  ShiftStats,
  Simulation,
  WorkplaceProfile,
} from "@/types";

import { displayDate } from "@/components/DateInput";
import { hebrewWeekday } from "@/components/Management/Calendar";

import type { AgentTouch } from "./agentTouch";
import { collectTouches } from "./agentTouch";
import { BoardGrid } from "./BoardGrid";
import { ConfirmDrop } from "./ConfirmDrop";
import { CoverageBar } from "./CoverageBar";
import { FilterBar } from "./FilterBar";
import { GenerateDialog } from "./GenerateDialog";
import { GenerateDayDialog } from "./GenerateDayDialog";
import { orderByHours } from "./shiftOrder";
import { EditorTarget, ShiftEditor } from "./ShiftEditor";
import { WeekNav } from "./WeekNav";
import { WeekRail } from "./WeekRail";
import { useBoard, weekDates } from "./useBoard";
import { useBoardKeys } from "./useBoardKeys";

/** The manager's operational home screen.
 *
 *  This is where a manager with a finished interview lands, and it opens on
 *  the week containing today in *their* timezone — the week they are working
 *  in is the only week worth defaulting to. The control room, the roster and
 *  the conversation with the agent are all still there, one click away
 *  through the header; the board is what is in front of them first.
 *
 *  **Everything on this screen works without the model.** The grid, the
 *  week arithmetic, the coverage figures, the filters, creating a shift,
 *  editing one, dragging one, and every validation and alternative offered
 *  is either arithmetic in the browser or a call to `bl/placement.py` /
 *  `bl/audit.py`, neither of which contains an LLM call. The agent is what
 *  makes this conversational — it explains, it notices, it proposes in
 *  words — and none of that is load-bearing for getting a week scheduled.
 *
 *  The decisions this screen is bound by are unchanged, and it goes out of
 *  its way not to route around them:
 *
 *  - **A drag proposes; the dialog writes** (D12). The drop opens
 *    `ConfirmDrop`, which collects the manager's reason (D8) — now with the
 *    consequences shown before the click rather than after.
 *  - **Filling an empty cell writes immediately** (D18), because it takes
 *    nothing from anybody.
 *  - **Warnings never block** (D3). Every save button here is live whatever
 *    the audit found.
 *  - **A draft is not published by editing it.** Publishing stays the
 *    separate, deliberate act it was.
 */
export function Board({
  overview,
  busy,
  generating,
  onGenerate,
  onGenerateDay,
  onOpenBlank,
  onAssign,
  onUnassign,
  onMove,
  onPublish,
  onExport,
  onOpenAgent,
  onPeriodChange,
  agent,
  dark,
}: {
  overview: ManagementOverview | undefined;
  busy: boolean;
  /** A period is being built in the background.
   *
   *  Separate from `busy` because it does not stop the board: the manager
   *  keeps placing shifts by hand while the agent works, and what they place
   *  becomes a pin the agent fills around (D18). Only the two controls that
   *  would collide with the build itself — starting another one, and
   *  rebuilding a single day inside it — read this. */
  generating: boolean;
  onGenerate: (input: {
    starts_on?: string;
    ends_on?: string;
    instructions?: string;
    required_assignments?: RequiredAssignment[];
  }) => void;
  onGenerateDay: (input: {
    schedule_id: string;
    date: string;
    instructions?: string;
  }) => void;
  onOpenBlank: (input: { starts_on?: string; ends_on?: string }) => void;
  /** Every hand-write names the period it happened on.
   *
   *  Not optional, and not left to the server to infer. Without it the
   *  backend resolves "the period covering today", so every one of these on
   *  any other week was refused — while `check`, the one call that always
   *  sent the id, had just told the manager the placement was fine. */
  onAssign: (input: {
    shift_name: string;
    slot_date: string;
    employee: string;
    reason?: string;
    schedule_id?: string;
  }) => Promise<void> | void;
  onUnassign: (input: {
    assignment_id: string;
    reason?: string;
    schedule_id?: string;
  }) => Promise<void> | void;
  onMove: (input: {
    assignment_id: string;
    shift_name: string;
    slot_date: string;
    reason: string;
    schedule_id?: string;
  }) => Promise<void> | void;
  onPublish: (scheduleId: string, published: boolean) => void;
  onExport: (scheduleId: string) => void;
  /** Which period this board is showing, whenever that changes.
   *
   *  The overview only ever hands over the period covering today, so
   *  everything outside this component that aimed at "the schedule" aimed at
   *  the wrong week the moment the manager paged away. The board is the only
   *  thing that knows which week is on screen, so it is what says so. */
  onPeriodChange?: (scheduleId: string) => void;
  /** Open the conversation with the agent — the control room beside this. */
  onOpenAgent?: () => void;
  /** What the agent is currently saying, so the week can show *where* it
   *  applies. Read-only: the board renders these and produces none of them,
   *  which is what keeps a highlight a description of the conversation
   *  rather than a second way to change a schedule. */
  agent?: {
    simulation: Simulation | null;
    proposal: Proposal | null;
    answer: AgentAnswer | null;
  };
  dark: boolean;
}) {
  const current = overview?.schedule ?? null;
  const board = useBoard(current?.id);

  // Which schedule this week actually shows. The overview hands over the
  // *current* period, so a manager sitting on this week costs no extra
  // request; paging away is what makes `/at` the source.
  const schedule: Schedule | null = useMemo(() => {
    if (current && covers(current, board.weekStart, board.weekEnd)) {
      return current;
    }
    return board.weekSchedule;
  }, [current, board.weekSchedule, board.weekStart, board.weekEnd]);

  // Whether the *schedule area* has nothing to draw yet.
  //
  // Not simply `board.weekBusy`. The overview hands over the current period,
  // so a manager sitting on this week has the schedule in hand while `/at`
  // is still confirming it — and putting a skeleton over a week that is
  // already on screen would make the common case flash on every refetch.
  // The board is loading only when it is waiting *and has nothing to show*.
  const showingLoader = board.weekBusy && !schedule;
  // Likewise a failed refresh with last-known-good data still on screen is
  // not a screen the manager needs taken away from them. The error card
  // replaces the board only when there is no board to replace.
  const showingError = !board.weekBusy && Boolean(board.weekError) && !schedule;

  // Report the period on screen upward. In an effect rather than inside the
  // memo above, because it is a notification and not part of computing what
  // to render.
  useEffect(() => {
    onPeriodChange?.(schedule?.id ?? "");
  }, [schedule?.id, onPeriodChange]);

  // Where on the week what the agent is saying actually applies. Derived
  // from the panels' own state rather than from anything new on the wire:
  // there is no field here `apply` could read, which is the same guard the
  // briefing and the answer already carry (D15/D19).
  const touches = useMemo(
    () =>
      collectTouches({
        simulation: agent?.simulation ?? null,
        proposal: agent?.proposal ?? null,
        answer: agent?.answer ?? null,
      }),
    [agent?.simulation, agent?.proposal, agent?.answer],
  );

  const roster = useMemo(
    () =>
      (overview?.employees ?? [])
        .map((row) => (typeof row.name === "string" ? row.name.trim() : ""))
        .filter(Boolean),
    [overview?.employees],
  );

  const roles = useMemo(() => {
    const map: Record<string, string> = {};
    for (const row of overview?.employees ?? []) {
      const name = typeof row.name === "string" ? row.name.trim() : "";
      const role = typeof row.role === "string" ? row.role.trim() : "";
      if (name) map[name] = role;
    }
    return map;
  }, [overview?.employees]);

  const roleOptions = useMemo(
    () => Array.from(new Set(Object.values(roles).filter(Boolean))).sort(),
    [roles],
  );
  // Who each person is, for the card's identity lines. One map rather than
  // one per fact: they are read together, on the same line, about the same
  // person, and a card that had to look up four maps to describe somebody
  // would drift the moment one of them was passed and another forgotten.
  const people = useMemo(() => {
    const map: Record<string, CardPerson> = {};
    for (const row of overview?.employees ?? []) {
      const name = typeof row.name === "string" ? row.name.trim() : "";
      if (!name) continue;
      map[name] = {
        role: typeof row.role === "string" ? row.role.trim() : "",
        rotation: rotationLabel(row.exit_pattern, row.rotation_group),
        is_shift_manager: Boolean(row.is_shift_manager),
        is_overlap: row.service_type === "overlap",
      };
    }
    return map;
  }, [overview?.employees]);

  // The filter's shift list reads in the same order the board's rows do —
  // by the clock. A dropdown that disagrees with the grid beside it is the
  // same confusion the row order was fixed for, one control over.
  const shiftOptions = useMemo(() => {
    const seen = new Set<string>();
    const startTimes: Record<string, string> = {};
    for (const slot of schedule?.slots ?? []) {
      seen.add(slot.shift_name);
      if (slot.start_time && !startTimes[slot.shift_name]) {
        startTimes[slot.shift_name] = slot.start_time;
      }
    }
    return orderByHours(Array.from(seen), startTimes);
  }, [schedule?.slots]);

  // A drop parks the intended move here and opens the confirmation. Nothing
  // has reached the server at this point — the dialog is what writes (D12).
  const [pendingMove, setPendingMove] = useState<{
    assignment: Assignment;
    shift_name: string;
    slot_date: string;
  } | null>(null);
  const [editor, setEditor] = useState<EditorTarget | null>(null);
  const [check, setCheck] = useState<PlacementCheck | null>(null);
  const [checking, setChecking] = useState(false);
  const [generationOpen, setGenerationOpen] = useState(false);
  const [generationDay, setGenerationDay] = useState<string | null>(null);

  // Every check is answered against the request that is still the newest.
  // Without this, a manager clicking through a dropdown gets whichever
  // response happens to land last, which may describe a choice they already
  // moved past.
  const checkToken = useRef(0);

  const runCheck = useCallback(
    async (input: {
      employee: string;
      shift_name: string;
      slot_date: string;
      moving_assignment_id?: string;
    }) => {
      const token = ++checkToken.current;
      setChecking(true);
      const result = await board.check({
        ...input,
        schedule_id: schedule?.id,
      });
      if (token !== checkToken.current) return;
      setCheck(result);
      setChecking(false);
    },
    [board, schedule?.id],
  );

  /** Open the confirmation for a proposed move, and check it.
   *
   *  Both halves happen here rather than in an effect watching `pendingMove`:
   *  a check is a *consequence of the gesture*, not a synchronisation with
   *  something outside React, and clearing the stale verdict is part of
   *  opening the dialog rather than a second render's job. */
  const openMove = useCallback(
    (move: {
      assignment: Assignment;
      shift_name: string;
      slot_date: string;
    }) => {
      setPendingMove(move);
      setCheck(null);
      void runCheck({
        employee: move.assignment.employee,
        shift_name: move.shift_name,
        slot_date: move.slot_date,
        moving_assignment_id: move.assignment.id,
      });
    },
    [runCheck],
  );

  /** Close whichever dialog is open, and drop its verdict with it.
   *
   *  One function for both because a verdict outliving the dialog that
   *  produced it is the bug: reopening the editor on a different cell would
   *  flash the previous cell's warning before the new check answers. The
   *  token bump makes any in-flight check land as stale. */
  const closeDialogs = useCallback(() => {
    checkToken.current += 1;
    setPendingMove(null);
    setEditor(null);
    setCheck(null);
    setChecking(false);
  }, []);

  const stats = overview?.stats ?? EMPTY_STATS;
  const constraints: Constraint[] = overview?.availability ?? [];

  // Arrow keys page the week; `T` returns to today. Disabled while a dialog
  // is open — the confirmation owns the keyboard then, and paging underneath
  // it would leave it describing a cell no longer on screen.
  useBoardKeys({
    onPrevious: board.previousWeek,
    onNext: board.nextWeek,
    onToday: board.goToToday,
    enabled: !pendingMove && !editor && !generationOpen && !generationDay,
  });

  // The figures for the week on screen. The overview computed them for the
  // *current* period; a week the manager paged to counts itself. Memoised
  // because that count walks the slot and assignment lists, and it has no
  // reason to run again while neither changed.
  const shownStats = useMemo(
    () => (schedule && schedule.id !== current?.id ? statsFor(schedule) : stats),
    [schedule, current?.id, stats],
  );

  return (
    <div className="board">
      <div className="board-head">
        <WeekNav
          weekStart={board.weekStart}
          weekEnd={board.weekEnd}
          isCurrentWeek={board.isCurrentWeek}
          busy={busy || board.weekBusy}
          onPrevious={board.previousWeek}
          onNext={board.nextWeek}
          onToday={board.goToToday}
        />

        <div className="board-head-actions">
          {schedule ? (
            <span className={`board-status is-${schedule.status}`}>
              {schedule.status === "published" ? "פורסם" : "טיוטה"}
            </span>
          ) : null}
          {onOpenAgent ? (
            <button
              type="button"
              className={`ghost-button${touches.size ? " is-live" : ""}`}
              onClick={onOpenAgent}
              title={
                touches.size
                  ? `הסוכן מתייחס ל-${touches.size} משמרות בשבוע הזה`
                  : "שיחה עם הסוכן על הסידור"
              }
            >
              <Sparkles size={14} />
              הסוכן
              {/* The count is what connects the two screens. The panels
                  themselves live in the control room, so without it a
                  manager on the board can see cells lit and have no idea
                  where the sentence explaining them is. */}
              {touches.size ? (
                <span className="board-agent-count">{touches.size}</span>
              ) : null}
            </button>
          ) : null}
          {schedule ? (
            <button
              type="button"
              className="ghost-button"
              onClick={() => onExport(schedule.id)}
              disabled={busy}
              title="הורדת הסידור כקובץ אקסל"
            >
              <Download size={14} />
              אקסל
            </button>
          ) : null}
          {schedule ? (
            <button
              type="button"
              className="ghost-button"
              onClick={() =>
                onPublish(schedule.id, schedule.status !== "published")
              }
              disabled={busy}
            >
              {schedule.status === "published" ? (
                <>
                  <EyeOff size={14} />
                  החזרה לטיוטה
                </>
              ) : (
                <>
                  <Eye size={14} />
                  פרסום לצוות
                </>
              )}
            </button>
          ) : null}
        </div>
      </div>

      <WeekRail
        weekStart={board.weekStart}
        today={board.today}
        schedule={schedule}
        busy={showingLoader}
      />

      {/* Loading first, and *before* the empty state.
          A week the manager paged to is unknown until `/at` answers, and
          `schedule` is null for both "still reading" and "nothing stored
          here". Falling straight through to `EmptyWeek` showed the second
          answer while the first was still true — a card headed "אין סידור
          לשבוע הזה", offering to build a week that may already exist, for
          as long as the request took. The skeleton holds that ground until
          there is an actual answer to render. */}
      {showingLoader ? (
        <BoardLoading weekStart={board.weekStart} weekEnd={board.weekEnd} />
      ) : showingError ? (
        <BoardLoadError
          message={board.weekError ?? ""}
          onRetry={() => void board.reloadWeek()}
        />
      ) : schedule ? (
        <>
          <CoverageBar
            // The figures describe the *current* period, which is what the
            // overview computed. A week the manager paged to carries its own
            // warnings on the schedule itself, so the tiles fall back to
            // counting that rather than reporting another week's totals.
            stats={shownStats}
            warnings={schedule.warnings}
            conflictsActive={board.filters.conflictsOnly}
            unassignedActive={board.filters.unassignedOnly}
            onFocusConflicts={() =>
              board.setFilters({
                conflictsOnly: !board.filters.conflictsOnly,
                unassignedOnly: false,
              })
            }
            onFocusUnassigned={() =>
              board.setFilters({
                unassignedOnly: !board.filters.unassignedOnly,
                conflictsOnly: false,
              })
            }
          />

          {schedule.status === "published" ? (
            <div className="board-published-lock" role="status">
              <LockKeyhole size={16} />
              <span>
                הסידור שמור לצוות. כדי לערוך שיבוצים, יש להחזיר אותו לטיוטה.
              </span>
              <button
                type="button"
                className="ghost-button"
                onClick={() => onPublish(schedule.id, false)}
                disabled={busy}
              >
                <EyeOff size={14} />
                החזרה לטיוטה
              </button>
            </div>
          ) : null}

          {/* What the agent is currently pointing at, named. The cells
              carry the outline; this says which of the three kinds of
              attention lit them and where the sentence itself is. It
              proposes nothing — the only button on it changes screens. */}
          {touches.size ? (
            <AgentTouchBar
              touches={touches}
              onOpenAgent={onOpenAgent}
            />
          ) : null}

          <FilterBar
            filters={board.filters}
            employees={roster}
            roles={roleOptions}
            shifts={shiftOptions}
            active={board.filtersActive}
            onChange={board.setFilters}
            onClear={board.clearFilters}
          />

          <BoardGrid
              schedule={schedule}
              weekStart={board.weekStart}
              today={board.today}
              constraints={constraints}
              employees={roster}
              roles={roles}
              people={people}
              filters={board.filters}
              dark={dark}
              readOnly={schedule.status === "published"}
              touches={touches}
              onDropCard={openMove}
              onDropEmployee={(input) =>
                void onAssign({ ...input, schedule_id: schedule.id })}
              onOpenCard={(assignment) => {
                setCheck(null);
                setEditor({ mode: "edit", assignment });
              }}
              onAddShift={(input) => {
                setCheck(null);
                setEditor({
                  mode: "create",
                  shift_name: input.shift_name,
                  slot_date: input.slot_date,
                });
              }}
              onGenerateDay={
                schedule.status === "draft" && !busy && !generating
                  ? (date) => setGenerationDay(date)
                  : undefined}
          />
        </>
      ) : (
        <EmptyWeek
          busy={busy || board.weekBusy}
          generating={generating}
          profile={overview?.profile ?? null}
          weekStart={board.weekStart}
          weekEnd={board.weekEnd}
          onGenerate={() => setGenerationOpen(true)}
          onOpenBlank={() =>
            onOpenBlank({ starts_on: board.weekStart, ends_on: board.weekEnd })
          }
        />
      )}

      {pendingMove ? (
        <ConfirmDrop
          assignment={pendingMove.assignment}
          shiftName={pendingMove.shift_name}
          slotDate={pendingMove.slot_date}
          check={check}
          checking={checking}
          busy={busy}
          onCancel={closeDialogs}
          onPickAlternativeSlot={(picked) =>
            openMove({
              assignment: pendingMove.assignment,
              shift_name: picked.shift_name,
              slot_date: picked.slot_date,
            })
          }
          onConfirm={(reason) => {
            void onMove({
              assignment_id: pendingMove.assignment.id,
              shift_name: pendingMove.shift_name,
              slot_date: pendingMove.slot_date,
              reason,
              schedule_id: schedule?.id,
            });
            closeDialogs();
          }}
        />
      ) : null}

      {editor && schedule ? (
        <ShiftEditor
          target={editor}
          schedule={schedule}
          employees={roster}
          roles={roles}
          busy={busy}
          check={check}
          checking={checking}
          onCheck={runCheck}
          onAssign={(input) => {
            void onAssign({
              shift_name: input.shift_name,
              slot_date: input.slot_date,
              employee: input.employee,
              reason: input.reason,
              schedule_id: schedule.id,
            });
            closeDialogs();
          }}
          onMove={(input) => {
            // Handed to the same dialog a drag opens: the editor is a
            // different gesture, not a different rule (D12).
            setEditor(null);
            openMove(input);
          }}
          onUnassign={(input) => {
            void onUnassign({
              assignment_id: input.assignment.id,
              reason: input.reason,
              schedule_id: schedule.id,
            });
            closeDialogs();
          }}
          onDuplicate={(input) => {
            void onAssign({
              shift_name: input.shift_name,
              slot_date: input.slot_date,
              employee: input.employee,
              reason: "שוכפל משיבוץ קיים",
              schedule_id: schedule.id,
            });
            closeDialogs();
          }}
          onClose={closeDialogs}
        />
      ) : null}

      {generationOpen ? (
        <GenerateDialog
          employees={roster}
          shifts={overview?.shifts ?? []}
          weekStart={board.weekStart}
          weekEnd={board.weekEnd}
          busy={busy || generating}
          onCancel={() => setGenerationOpen(false)}
          onConfirm={(input) => {
            onGenerate(input);
            setGenerationOpen(false);
          }}
        />
      ) : null}

      {generationDay && schedule ? (
        <GenerateDayDialog
          date={generationDay}
          busy={busy || generating}
          onCancel={() => setGenerationDay(null)}
          onConfirm={(instructions) => {
            onGenerateDay({
              schedule_id: schedule.id,
              date: generationDay,
              instructions,
            });
            setGenerationDay(null);
          }}
        />
      ) : null}
    </div>
  );
}

/** Whether a stored period covers the displayed week at all.
 *
 *  Overlap rather than equality: a fortnight-long period contains this week
 *  without matching its bounds, and demanding an exact match would send the
 *  board fetching a period it already has. */
/** The line between the conversation and the week.
 *
 *  The agent's cards live in the control room; the manager lives on this
 *  board. Without something naming the connection, a lit cell is a mystery
 *  and the sentence explaining it is one screen away with nothing pointing
 *  at it. This says what kind of attention is on the week, how much of it,
 *  and offers the one action that makes sense here — going to read it.
 *
 *  **It carries no operation and no confirm.** Approving a simulation or a
 *  proposal happens where it always did, with the manager's reason
 *  (D8/D12/D20). A shortcut from this bar to a write is precisely the
 *  second write path those decisions exist to prevent. */
function AgentTouchBar({
  touches,
  onOpenAgent,
}: {
  touches: Map<string, AgentTouch[]>;
  onOpenAgent?: () => void;
}) {
  // Counted by origin rather than listed: a week where the agent touched
  // nine cells needs a sentence, not nine chips.
  const counts = { proposal: 0, simulation: 0, answer: 0 };
  for (const list of touches.values()) {
    const strongest = list[list.length - 1];
    counts[strongest.origin] += 1;
  }

  const said: string[] = [];
  if (counts.proposal) said.push(`מציע שינוי ב-${counts.proposal} משמרות`);
  if (counts.simulation) {
    said.push(`מדמה שינוי ב-${counts.simulation} משמרות`);
  }
  if (counts.answer) said.push(`בדק ${counts.answer} משמרות כדי לענות`);

  return (
    <div className="board-agent-bar" role="status">
      <Sparkles size={14} />
      <span className="board-agent-bar-text">
        הסוכן {said.join(", ")} — מסומן על הלוח.
      </span>
      {onOpenAgent ? (
        <button type="button" className="ghost-button" onClick={onOpenAgent}>
          מעבר לשיחה
        </button>
      ) : null}
    </div>
  );
}

/** Whether this period is the one to render for the displayed week.
 *
 *  Containment, not overlap, and the difference is a bug this used to have.
 *  `starts_on <= end && ends_on >= start` is true when a period touches the
 *  week by a single day, so paging off the end of a period kept the old
 *  period on screen — rendered *as* the new week, with no loading state,
 *  until `/at` answered. The server resolves a day by containment
 *  (`schedule_service.period_at`), and the two rules have to agree: a period
 *  the board would not get back from `/at` for this week is not this week's
 *  schedule, whatever it overlaps.
 *
 *  Both bounds are checked because a week is a range. A period covering only
 *  part of the week is not a stand-in for it either — the missing days would
 *  render as empty columns rather than as the unread days they are. */
function covers(schedule: Schedule, start: string, end: string): boolean {
  return schedule.starts_on <= start && schedule.ends_on >= end;
}

/** The tiles for a period the overview did not compute.
 *
 *  Counted off the schedule's own slots and assignments — the same two lists
 *  `audit.py` counts — so a paged-to week reports itself rather than
 *  borrowing the current period's totals. Coverage and gaps only: hours need
 *  the profile's shift lengths and weights, and guessing those in the
 *  browser is exactly the second implementation the stats panel exists to
 *  avoid. The four tiles that would be fiction read zero rather than wrong. */
function statsFor(schedule: Schedule): ShiftStats {
  const required = schedule.slots.reduce(
    (total, slot) => total + (slot.headcount || 0),
    0,
  );
  const assigned = schedule.assignments.length;
  const unfilled = schedule.slots.filter(
    (slot) =>
      schedule.assignments.filter(
        (row) => row.shift === slot.shift_name && row.date === slot.slot_date,
      ).length < (slot.headcount || 0),
  ).length;

  return {
    ...EMPTY_STATS,
    total_shifts: assigned,
    people_working: new Set(schedule.assignments.map((row) => row.employee))
      .size,
    coverage: {
      required,
      assigned,
      unfilled_slots: unfilled,
      percent: required ? Math.round((assigned / required) * 100) : 100,
    },
  };
}

const EMPTY_STATS: ShiftStats = {
  total_hours: 0,
  total_shifts: 0,
  people_working: 0,
  coverage: { required: 0, assigned: 0, unfilled_slots: 0, percent: 100 },
  by_shift: [],
  by_day: [],
  by_employee: [],
  warning_counts: [],
  constraint_pressure: { blocked: 0, people: 0, conflicts: 0, honored: 0 },
};

/** The board while the week on screen is still being read.
 *
 *  A skeleton of the grid rather than a bare spinner, and it stands where
 *  `BoardGrid` will: the shift rows and seven day columns are the shape the
 *  manager is already looking for, so the screen does not jump when the
 *  answer lands. Days are named from `weekStart` alone — the same arithmetic
 *  the real grid uses — which is what lets the dates be right for the newly
 *  selected week before anything has been fetched for it.
 *
 *  Scoped to the schedule area on purpose. The week nav above it stays live,
 *  so paging on through a slow week is possible rather than blocked by the
 *  wait it caused; a full-screen block would take the manager's own controls
 *  away at exactly the moment they are most likely to use them.
 *
 *  `role="status"` rather than `alert`: a screen reader is told the week is
 *  loading once, without the interruption an alert carries. */
function BoardLoading({
  weekStart,
  weekEnd,
}: {
  weekStart: string;
  weekEnd: string;
}) {
  const dates = weekDates(weekStart);

  return (
    <div className="board-loading" role="status" aria-busy="true">
      <p className="board-loading-line">
        <LoaderCircle className="spin" size={16} aria-hidden="true" />
        טוען את השיבוצים לשבוע…
      </p>

      {/* Marked hidden from assistive tech: the line above already says
          what is happening, and a screen reader walking twenty-one empty
          placeholder cells is noise, not information. */}
      <div className="board-loading-grid" aria-hidden="true">
        <div className="board-loading-row is-head">
          <div className="board-loading-corner" />
          {dates.map((date) => (
            <div key={date} className="board-loading-day">
              <strong>{hebrewWeekday(date)}</strong>
              <span>{displayDate(date)}</span>
            </div>
          ))}
        </div>
        {SKELETON_ROWS.map((row) => (
          <div key={row} className="board-loading-row">
            <div className="board-loading-shift" />
            {dates.map((date) => (
              <div key={date} className="board-loading-cell" />
            ))}
          </div>
        ))}
      </div>

      <p className="board-loading-range">
        {weekStart} – {weekEnd}
      </p>
    </div>
  );
}

/** How many shift rows the skeleton draws.
 *
 *  Three, not the real count: the shift vocabulary comes from the schedule
 *  being fetched, so there is nothing to count yet. Three is enough to read
 *  as a grid and few enough that a workplace with two shifts does not watch
 *  the board shrink when the answer arrives. */
const SKELETON_ROWS = [0, 1, 2];

/** The week could not be read.
 *
 *  Distinct from `EmptyWeek`, and the distinction is the whole point. An
 *  empty week offers to build one, because there is genuinely nothing
 *  stored for it; this says the question went unanswered and offers to ask
 *  again. Handing a manager a "build the week" button because the network
 *  blinked invites them to generate over a schedule that already exists.
 *
 *  It is a terminal state with a way out — the loading state always ends
 *  here or at a rendered week, never in a spinner nobody can leave. */
function BoardLoadError({
  message,
  onRetry,
}: {
  message: string;
  onRetry: () => void;
}) {
  return (
    <div className="board-empty board-load-error" role="alert">
      <h2>
        <AlertTriangle size={18} aria-hidden="true" />
        לא הצלחנו לטעון את הסידור
      </h2>
      <p>
        השבוע הזה לא נקרא מהשרת, כך שאיננו יודעים אם יש בו סידור. אפשר לנסות
        שוב — שום דבר לא נכתב ולא נמחק.
      </p>
      <p className="board-load-error-detail">{message}</p>
      <div className="board-empty-actions">
        <button type="button" className="primary-button" onClick={onRetry}>
          <RefreshCw size={14} aria-hidden="true" />
          ניסיון חוזר
        </button>
      </div>
    </div>
  );
}

/** A week with no schedule stored against it.
 *
 *  Both doors are offered side by side because they are the two halves of
 *  D6 and neither is the fallback for the other: the agent builds one, or
 *  the manager opens an empty grid and fills it in with no model involved.
 *  The dates are the week on screen, so paging to next week and pressing
 *  "build" builds *that* week rather than today's. */
function EmptyWeek({
  busy,
  generating,
  profile,
  weekStart,
  weekEnd,
  onGenerate,
  onOpenBlank,
}: {
  busy: boolean;
  generating: boolean;
  profile: WorkplaceProfile | null;
  weekStart: string;
  weekEnd: string;
  onGenerate: () => void;
  onOpenBlank: () => void;
}) {
  if (!profile) {
    return (
      <div className="board-empty">
        <h2>צריך להשלים את ראיון ההיכרות</h2>
        <p>
          הראיון הוא מה שמלמד את הסוכן את המשמרות, העובדים והכללים. בלעדיו אין
          ממה לבנות סידור — גם לא ידנית, כי המשמרות עצמן מגיעות משם.
        </p>
      </div>
    );
  }

  // A profile exists but its interview was ended early. The distinction that
  // matters is the shift vocabulary: without it there is no grid at all, not
  // even one built by hand, because inventing shift names is what D9
  // forbids. Everything else missing degrades the result rather than
  // preventing it, so the week still opens and the gaps are stated.
  const gaps = profile.completeness;
  if (gaps && !gaps.complete && !profile.shifts?.length) {
    return (
      <div className="board-empty">
        <h2>עוד לא הוגדרו סוגי משמרות</h2>
        <p>
          הראיון נסגר לפני שהוגדרו המשמרות, ובלי סוגי המשמרות אין שורות לבנות
          מהן לוח — גם לא ידנית. אפשר לחזור לראיון מהכפתור בסרגל העליון
          ולהשלים אותן.
        </p>
      </div>
    );
  }

  return (
    <div className="board-empty">
      <h2>אין סידור לשבוע הזה</h2>
      <p>
        אפשר לבקש מהסוכן לבנות את השבוע, או לפתוח שבוע ריק ולשבץ ידנית — בלי
        הסוכן בכלל.
      </p>
      {gaps && !gaps.complete ? (
        <p className="board-empty-partial">
          הראיון עוד לא הושלם, כך שהסוכן בונה על סמך מה שהספיק ללמוד. אפשר
          לשאול אותו בחדר הבקרה מה עוד חסר לו.
        </p>
      ) : null}
      <div className="board-empty-actions">
        <button
          type="button"
          className="ghost-button"
          onClick={onOpenBlank}
          disabled={busy || generating}
          title="פתיחת שבוע ריק לשיבוץ ידני"
        >
          <PencilLine size={14} />
          שבוע ריק
        </button>
        <button
          type="button"
          className="primary-button"
          onClick={onGenerate}
          disabled={busy || generating}
        >
          {generating ? "בונה…" : "בניית הסידור לשבוע"}
        </button>
      </div>
      <p className="board-empty-range">
        {weekStart} – {weekEnd}
      </p>
    </div>
  );
}
