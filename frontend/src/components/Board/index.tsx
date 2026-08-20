"use client";

import { Download, Eye, EyeOff, PencilLine, Sparkles } from "lucide-react";
import { useCallback, useMemo, useRef, useState } from "react";

import type {
  Assignment,
  Constraint,
  ManagementOverview,
  PlacementCheck,
  Schedule,
  ShiftStats,
  WorkplaceProfile,
} from "@/types";

import { BoardGrid } from "./BoardGrid";
import { ConfirmDrop } from "./ConfirmDrop";
import { CoverageBar } from "./CoverageBar";
import { FilterBar } from "./FilterBar";
import { EditorTarget, ShiftEditor } from "./ShiftEditor";
import { WeekNav } from "./WeekNav";
import { useBoard } from "./useBoard";

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
  onGenerate,
  onOpenBlank,
  onAssign,
  onUnassign,
  onMove,
  onPublish,
  onExport,
  onOpenAgent,
  dark,
}: {
  overview: ManagementOverview | undefined;
  busy: boolean;
  onGenerate: (input: { starts_on?: string; ends_on?: string }) => void;
  onOpenBlank: (input: { starts_on?: string; ends_on?: string }) => void;
  onAssign: (input: {
    shift_name: string;
    slot_date: string;
    employee: string;
    reason?: string;
  }) => Promise<void> | void;
  onUnassign: (input: {
    assignment_id: string;
    reason?: string;
  }) => Promise<void> | void;
  onMove: (input: {
    assignment_id: string;
    shift_name: string;
    slot_date: string;
    reason: string;
  }) => Promise<void> | void;
  onPublish: (scheduleId: string, published: boolean) => void;
  onExport: (scheduleId: string) => void;
  /** Open the conversation with the agent — the control room beside this. */
  onOpenAgent?: () => void;
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

  const shiftOptions = useMemo(() => {
    const seen = new Set<string>();
    for (const slot of schedule?.slots ?? []) seen.add(slot.shift_name);
    return Array.from(seen);
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
              className="ghost-button"
              onClick={onOpenAgent}
              title="שיחה עם הסוכן על הסידור"
            >
              <Sparkles size={14} />
              הסוכן
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

      {schedule ? (
        <>
          <CoverageBar
            stats={
              // The figures describe the *current* period, which is what the
              // overview computed. A week the manager paged to carries its
              // own warnings on the schedule itself, so the tiles fall back
              // to counting that rather than reporting another week's totals.
              schedule.id === current?.id ? stats : statsFor(schedule)
            }
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

          <FilterBar
            filters={board.filters}
            employees={roster}
            roles={roleOptions}
            shifts={shiftOptions}
            active={board.filtersActive}
            onChange={board.setFilters}
            onClear={board.clearFilters}
          />

          {/* Status is a property of the period, so filtering by it either
              shows the whole board or none of it. Said rather than silently
              rendering an empty grid. */}
          {board.filters.status !== "all" &&
          board.filters.status !== schedule.status ? (
            <p className="board-empty-filtered">
              הסידור בשבוע הזה הוא{" "}
              {schedule.status === "published" ? "מפורסם" : "טיוטה"}, והסינון
              מבקש {board.filters.status === "published" ? "מפורסם" : "טיוטה"}.
            </p>
          ) : (
            <BoardGrid
              schedule={schedule}
              weekStart={board.weekStart}
              today={board.today}
              constraints={constraints}
              employees={roster}
              roles={roles}
              filters={board.filters}
              dark={dark}
              onDropCard={openMove}
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
            />
          )}
        </>
      ) : (
        <EmptyWeek
          busy={busy || board.weekBusy}
          profile={overview?.profile ?? null}
          weekStart={board.weekStart}
          weekEnd={board.weekEnd}
          onGenerate={() =>
            onGenerate({ starts_on: board.weekStart, ends_on: board.weekEnd })
          }
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
            });
            closeDialogs();
          }}
          onDuplicate={(input) => {
            void onAssign({
              shift_name: input.shift_name,
              slot_date: input.slot_date,
              employee: input.employee,
              reason: "שוכפל משיבוץ קיים",
            });
            closeDialogs();
          }}
          onClose={closeDialogs}
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
function covers(schedule: Schedule, start: string, end: string): boolean {
  return schedule.starts_on <= end && schedule.ends_on >= start;
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

/** A week with no schedule stored against it.
 *
 *  Both doors are offered side by side because they are the two halves of
 *  D6 and neither is the fallback for the other: the agent builds one, or
 *  the manager opens an empty grid and fills it in with no model involved.
 *  The dates are the week on screen, so paging to next week and pressing
 *  "build" builds *that* week rather than today's. */
function EmptyWeek({
  busy,
  profile,
  weekStart,
  weekEnd,
  onGenerate,
  onOpenBlank,
}: {
  busy: boolean;
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
          disabled={busy}
          title="פתיחת שבוע ריק לשיבוץ ידני"
        >
          <PencilLine size={14} />
          שבוע ריק
        </button>
        <button
          type="button"
          className="primary-button"
          onClick={onGenerate}
          disabled={busy}
        >
          {busy ? "בונה…" : "בניית הסידור לשבוע"}
        </button>
      </div>
      <p className="board-empty-range">
        {weekStart} – {weekEnd}
      </p>
    </div>
  );
}
