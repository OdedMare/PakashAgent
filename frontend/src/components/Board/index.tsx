"use client";

import {
  AlertTriangle,
  CalendarPlus,
  Download,
  Eraser,
  Eye,
  EyeOff,
  LoaderCircle,
  LockKeyhole,
  PencilLine,
  RefreshCw,
  Sparkles,
  Trash2,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type {
  AgentAnswer,
  Assignment,
  CardPerson,
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
import type { RemovalTarget } from "./ConfirmRemoval";
import { ConfirmRemoval } from "./ConfirmRemoval";
import { CoverageBar } from "./CoverageBar";
import { sundayOf } from "./dates";
import { FilterBar } from "./FilterBar";
import { GenerateDialog } from "./GenerateDialog";
import { fillsASeat, rotationLabel } from "./person";
import { RangeGrid } from "./RangeGrid";
import { orderByHours } from "./shiftOrder";
import { EditorTarget, ShiftEditor } from "./ShiftEditor";
import { clipTo, mergePeriods } from "./span";
import { ViewSwitch } from "./ViewSwitch";
import { isOverview } from "./views";
import { WeekNav } from "./WeekNav";
import { WeekRail } from "./WeekRail";
import { addDays, useBoard, weekDates } from "./useBoard";
import { useBoardKeys } from "./useBoardKeys";

/** The manager's operational home screen.
 *
 *  This is where a manager with completed setup lands, and it opens on
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
 *  **Four widths, two kinds.** A day and a week are this board, aimed at the
 *  one period they sit inside, with everything above available. Two weeks
 *  and a month cross periods, so they are drawn by `RangeGrid` for reading
 *  and open a day or a week on click; the period's own actions — publish,
 *  clear, delete, export — are withheld there because there is no one
 *  period for them to mean (`views.ts`).
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
  onOpenDay,
  onOpenBlank,
  onAssign,
  onUnassign,
  onMove,
  onClear,
  onDelete,
  onPublish,
  onExport,
  onOpenAgent,
  onPeriodChange,
  navigateToWeek,
  onRefreshReady,
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
    /** The draft to build into. Without it a period is opened. */
    schedule_id?: string;
    starts_on?: string;
    ends_on?: string;
    /** The days the agent fills, when that is less than the new period. */
    build_from?: string;
    build_through?: string;
    instructions?: string;
    required_assignments?: RequiredAssignment[];
  }) => void;
  /** Open the agent conversation focused on one day, to give it
   *  instructions for that date. The chat is the only place the agent takes
   *  instructions; the board just points it at a day. */
  onOpenDay?: (date: string) => void;
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
  /** Empty a day's shifts, or the whole week's. The grid stays behind, so
   *  the week can be filled in again without rebuilding its slots. */
  onClear: (input: {
    schedule_id: string;
    slot_date?: string;
    reason?: string;
  }) => Promise<void> | void;
  /** Delete the week's period outright. Offered beside clearing rather than
   *  instead of it: they undo different things — one takes back what was
   *  assigned, the other takes back the week having been built at all. */
  onDelete: (scheduleId: string) => Promise<void> | void;
  onPublish: (scheduleId: string, published: boolean) => void;
  onExport: (scheduleId: string) => void;
  /** Which period this board is showing, whenever that changes.
   *
   *  The overview only ever hands over the period covering today, so
   *  everything outside this component that aimed at "the schedule" aimed at
   *  the wrong week the moment the manager paged away. The board is the only
   *  thing that knows which week is on screen, so it is what says so. */
  onPeriodChange?: (scheduleId: string, weekStart?: string) => void;
  navigateToWeek?: { date: string; n: number };
  onRefreshReady?: (refresh: ((date?: string) => Promise<void>) | null) => void;
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
  const board = useBoard(current?.id, navigateToWeek?.n);
  const refreshBoard = board.refresh;
  useEffect(() => {
    onRefreshReady?.(refreshBoard);
    return () => onRefreshReady?.(null);
  }, [onRefreshReady, refreshBoard]);
  const goToWeekOf = board.goToWeekOf;
  useEffect(() => {
    if (navigateToWeek?.date) goToWeekOf(navigateToWeek.date);
  }, [navigateToWeek, goToWeekOf]);

  // Which schedule this week actually shows. The overview hands over the
  // *current* period, so a manager sitting on this week costs no extra
  // request; paging away is what makes `/at` the source.
  const schedule: Schedule | null = useMemo(() => {
    if (current && covers(current, board.weekStart, board.weekEnd)) {
      return current;
    }
    return board.weekSchedule;
  }, [current, board.weekSchedule, board.weekStart, board.weekEnd]);

  // A day and a week are one period; two weeks and a month are several,
  // and are drawn for reading rather than for writing (`views.ts`).
  const overviewMode = isOverview(board.view);
  // The columns of the working board: the week, or the one day of it.
  // Memoised because the grid re-centres on today whenever these change, and
  // a fresh array per render would do that on every keystroke elsewhere.
  const dates = useMemo(
    () => (board.view === "day" ? [board.focus] : weekDates(board.weekStart)),
    [board.view, board.focus, board.weekStart],
  );
  // The periods under a two-week or month view, as one clipped span.
  const span = useMemo(
    () =>
      overviewMode
        ? mergePeriods(board.rangeSchedules, board.rangeStart, board.rangeEnd)
        : null,
    [overviewMode, board.rangeSchedules, board.rangeStart, board.rangeEnd],
  );

  // Writes refresh the overview; paged weeks and calendar ranges have their own reads.
  const { reloadWeek, reloadRange, invalidate } = board;
  const previousOverview = useRef(overview);
  useEffect(() => {
    const changed = previousOverview.current !== overview;
    previousOverview.current = overview;
    if (changed && overview) {
      invalidate();
      if (!current || !covers(current, board.weekStart, board.weekEnd)) void reloadWeek();
      void reloadRange();
    }
  }, [overview, current, board.weekStart, board.weekEnd, reloadWeek, reloadRange, invalidate]);

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
    onPeriodChange?.(schedule?.id ?? "", board.weekStart);
  }, [schedule?.id, board.weekStart, onPeriodChange]);

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
        counts_toward_staffing: fillsASeat(row),
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
    for (const slot of (overviewMode ? span : schedule)?.slots ?? []) {
      seen.add(slot.shift_name);
      if (slot.start_time && !startTimes[slot.shift_name]) {
        startTimes[slot.shift_name] = slot.start_time;
      }
    }
    return orderByHours(Array.from(seen), startTimes);
  }, [overviewMode, span, schedule]);

  // A drop parks the intended move here and opens the confirmation. Nothing
  // has reached the server at this point — the dialog is what writes (D12).
  const [pendingMove, setPendingMove] = useState<{
    assignment: Assignment;
    shift_name: string;
    slot_date: string;
  } | null>(null);
  const [editor, setEditor] = useState<EditorTarget | null>(null);
  // What the manager has asked to remove, held until they confirm. Nothing
  // has reached the server while this is set — the same shape a drop has,
  // for a gesture that is even harder to take back.
  const [removal, setRemoval] = useState<RemovalTarget | null>(null);
  const [check, setCheck] = useState<PlacementCheck | null>(null);
  const [checking, setChecking] = useState(false);
  // The run the build dialog is open on, or null while it is closed.
  // `inPeriod` is fixed by where it was opened from — a day's column head,
  // or the card of a week with nothing stored — so a period landing
  // underneath an open dialog cannot change what its button will do.
  const [building, setBuilding] = useState<{
    from: string;
    through: string;
    inPeriod: boolean;
  } | null>(null);

  // Every check is answered against the request that is still the newest.
  // Without this, a manager clicking through a dropdown gets whichever
  // response happens to land last, which may describe a choice they already
  // moved past.
  const checkToken = useRef(0);

  // Depend on `board.check`, not `board`: `useBoard` returns a fresh object
  // every render, and `ShiftEditor` re-checks whenever `onCheck` changes —
  // so depending on `board` made every answer trigger the next request, and
  // the verdict flickered between "checking" and the result forever.
  const boardCheck = board.check;
  const runCheck = useCallback(
    async (input: {
      employee: string;
      shift_name: string;
      slot_date: string;
      moving_assignment_id?: string;
    }) => {
      const token = ++checkToken.current;
      setChecking(true);
      const result = await boardCheck({
        ...input,
        schedule_id: schedule?.id,
      });
      if (token !== checkToken.current) return;
      setCheck(result);
      setChecking(false);
    },
    [boardCheck, schedule?.id],
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

  // Arrow keys page by whatever is on screen — a day, a week, a month; `T`
  // returns to today. Disabled while a dialog is open — the confirmation
  // owns the keyboard then, and paging underneath it would leave it
  // describing a cell no longer on screen.
  useBoardKeys({
    onPrevious: board.previous,
    onNext: board.next,
    onToday: board.goToToday,
    enabled:
      !pendingMove && !editor && !building && !removal,
  });

  // Whether this week can still be written to at all. Publishing locks the
  // board, and a build running on it owns the days it has not reached yet —
  // clearing underneath either would be racing something.
  const writable =
    Boolean(schedule) && schedule?.status === "draft" && !busy && !generating;

  // The figures for the week on screen. The overview computed them for the
  // *current* period; a week the manager paged to counts itself. Memoised
  // because that count walks the slot and assignment lists, and it has no
  // reason to run again while neither changed.
  //
  // A single day counts itself too, for the same reason in the other
  // direction: tiles reading "4 משמרות פתוחות" over a column with none open
  // would be the week's answer to a question about Tuesday. Its hours are
  // the one figure borrowed — `audit.py` already worked them out per date
  // for the current period, and that is the only place they are not a guess.
  const day = board.view === "day" ? board.focus : "";
  const shownStats = useMemo(() => {
    if (!schedule) return stats;
    const own = schedule.id === current?.id;
    if (!day) return own ? stats : statsFor(schedule, people);
    const counted = statsFor(clipTo(schedule, day, day), people);
    const load = own
      ? stats.by_day.find((row) => row.date === day)
      : undefined;
    return load ? { ...counted, total_hours: load.hours } : counted;
  }, [schedule, current?.id, stats, people, day]);
  const shownWarnings = useMemo(
    () =>
      schedule && day
        ? schedule.warnings.filter((row) => row.date === day)
        : (schedule?.warnings ?? []),
    [schedule, day],
  );
  const spanStats = useMemo(
    () => (span ? statsFor(span, people) : EMPTY_STATS),
    [span, people],
  );
  // The period the header's own actions act on. None under a two-week or
  // month view: "publish" and "clear the week" have no one period to mean
  // there, and guessing which is how the wrong week gets cleared.
  const period = overviewMode ? null : schedule;

  return (
    <div className="board">
      <div className="board-head">
        <div className="board-head-nav">
          <WeekNav
            view={board.view}
            focus={board.focus}
            rangeStart={board.rangeStart}
            rangeEnd={board.rangeEnd}
            isCurrent={board.isCurrent}
            busy={busy || (overviewMode ? board.rangeBusy : board.weekBusy)}
            onPrevious={board.previous}
            onNext={board.next}
            onToday={board.goToToday}
          />
          <ViewSwitch view={board.view} onChange={board.setView} />
        </div>

        <div className="board-head-actions" data-tour="board-actions">
          {period ? (
            <span className={`board-status is-${period.status}`}>
              {period.status === "published" ? "פורסם" : "טיוטה"}
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
          {period ? (
            <button
              type="button"
              className="ghost-button"
              onClick={() => onExport(period.id)}
              disabled={busy}
              title="הורדת הסידור כקובץ אקסל"
            >
              <Download size={14} />
              אקסל
            </button>
          ) : null}
          {/* Taking the week back. Two buttons because they undo two
              different things: clearing empties the grid the manager is
              looking at, deleting removes the period that grid belongs to.
              Both are withheld while the board is not writable — a published
              week refuses every write, and a running build owns the days it
              has not reached. */}
          {period && writable ? (
            <button
              type="button"
              className="ghost-button"
              onClick={() =>
                setRemoval({ mode: "week", count: period.assignments.length })
              }
              title="מחיקת כל השיבוצים בשבוע, בלי למחוק את שורות המשמרות"
            >
              <Eraser size={14} />
              ניקוי השבוע
            </button>
          ) : null}
          {period && writable ? (
            <button
              type="button"
              className="ghost-button is-danger"
              onClick={() =>
                setRemoval({
                  mode: "period",
                  count: period.assignments.length,
                })
              }
              title="מחיקת הסידור לשבוע הזה, כולל שורות המשמרות"
            >
              <Trash2 size={14} />
              מחיקת הסידור
            </button>
          ) : null}
          {period ? (
            <button
              type="button"
              className="ghost-button"
              onClick={() =>
                onPublish(period.id, period.status !== "published")
              }
              disabled={busy}
            >
              {period.status === "published" ? (
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

      {/* The rail is one week, so it belongs to the two views that are one
          week. Under a day view it is also what keeps the other six days in
          sight, and what moves between them. */}
      {overviewMode ? null : (
        <WeekRail
          weekStart={board.weekStart}
          today={board.today}
          schedule={schedule}
          busy={showingLoader}
          selected={day || undefined}
          onPickDay={board.openDay}
        />
      )}

      {/* Loading first, and *before* the empty state.
          A week the manager paged to is unknown until `/at` answers, and
          `schedule` is null for both "still reading" and "nothing stored
          here". Falling straight through to `EmptyWeek` showed the second
          answer while the first was still true — a card headed "אין סידור
          לשבוע הזה", offering to build a week that may already exist, for
          as long as the request took. The skeleton holds that ground until
          there is an actual answer to render. */}
      {overviewMode ? (
        board.rangeError ? (
          <BoardLoadError
            span
            message={board.rangeError}
            onRetry={() => void board.reloadRange()}
          />
        ) : (
          <>
            {/* Tiles and filters wait for something to count. The grid does
                not: its dates come from the view alone, so it stands in
                place while the span is read and says nothing about a day
                until there is an answer for it. */}
            {span ? (
              <>
                <CoverageBar
                  stats={spanStats}
                  warnings={span.warnings}
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
              </>
            ) : null}
            <RangeGrid
              start={board.rangeStart}
              end={board.rangeEnd}
              month={
                board.view === "month" ? board.focus.slice(0, 7) : undefined
              }
              today={board.today}
              span={span}
              periods={board.rangeSchedules}
              employees={roster}
              roles={roles}
              people={people}
              filters={board.filters}
              dark={dark}
              busy={board.rangeBusy}
              touches={touches}
              onOpenDay={board.openDay}
              onOpenWeek={board.openWeek}
            />
          </>
        )
      ) : showingLoader ? (
        <BoardLoading
          dates={dates}
          weekStart={board.weekStart}
          weekEnd={board.weekEnd}
        />
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
            warnings={shownWarnings}
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
              dates={dates}
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
              onRemoveCard={(assignment) =>
                void onUnassign({
                  assignment_id: assignment.id,
                  schedule_id: schedule.id,
                })}
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
              onOpenDay={onOpenDay}
              // "From this day until Saturday" — the rest of the week from
              // wherever the manager is standing in it. The dialog lets
              // them end it on any other day the period holds.
              onBuildFrom={
                writable
                  ? (date) =>
                      setBuilding({
                        from: date,
                        through: earlier(saturdayOf(date), schedule.ends_on),
                        inPeriod: true,
                      })
                  : undefined}
              onClearDay={
                writable
                  ? (date) =>
                      setRemoval({
                        mode: "day",
                        date,
                        count: schedule.assignments.filter(
                          (row) => row.date === date,
                        ).length,
                      })
                  : undefined}
              onOpenDate={board.openDay}
          />
        </>
      ) : (
        <EmptyWeek
          busy={busy || board.weekBusy}
          generating={generating}
          profile={overview?.profile ?? null}
          weekStart={board.weekStart}
          weekEnd={board.weekEnd}
          // The day a partial build would start on: the one on screen, or
          // today when this is today's week. On any other week there is no
          // day the manager is standing on, and the whole week is the offer.
          fromDay={
            day ||
            (board.today >= board.weekStart && board.today <= board.weekEnd
              ? board.today
              : "")
          }
          onGenerate={(from) =>
            setBuilding({
              from: from ?? board.weekStart,
              through: board.weekEnd,
              inPeriod: false,
            })
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
          inactiveFrom={Object.fromEntries((overview?.employees ?? []).filter((row) => row.inactive_from).map((row) => [String(row.name), String(row.inactive_from)]))}
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

      {building && (!building.inPeriod || schedule) ? (
        <GenerateDialog
          employees={roster}
          shifts={overview?.shifts ?? []}
          from={building.from}
          through={building.through}
          period={building.inPeriod ? schedule : null}
          busy={busy || generating}
          onCancel={() => setBuilding(null)}
          onConfirm={(input) => {
            onGenerate(
              building.inPeriod && schedule
                ? {
                    schedule_id: schedule.id,
                    starts_on: input.starts_on,
                    ends_on: input.ends_on,
                    instructions: input.instructions,
                  }
                : inWholeWeeks(input),
            );
            setBuilding(null);
          }}
        />
      ) : null}

      {removal && schedule ? (
        <ConfirmRemoval
          target={removal}
          busy={busy}
          onCancel={() => setRemoval(null)}
          onConfirm={(reason) => {
            if (removal.mode === "period") {
              void onDelete(schedule.id);
            } else {
              void onClear({
                schedule_id: schedule.id,
                slot_date: removal.mode === "day" ? removal.date : "",
                reason,
              });
            }
            setRemoval(null);
          }}
        />
      ) : null}

    </div>
  );
}

function saturdayOf(day: string): string {
  return addDays(sundayOf(day), 6);
}

function earlier(first: string, second: string): string {
  return first <= second ? first : second;
}

/** A new period for a run of days, widened to the weeks the run touches.
 *
 *  The board finds a week's period by its Sunday, so one opened from a
 *  Wednesday would be stored and never drawn — and the week would go on
 *  offering to be built. The period therefore takes the whole weeks, and the
 *  run itself travels beside it as what the agent is asked to fill; the days
 *  outside it open empty, like any cell nobody has been placed in yet. */
function inWholeWeeks<T extends { starts_on: string; ends_on: string }>(
  input: T,
): T & { build_from?: string; build_through?: string } {
  const starts_on = sundayOf(input.starts_on);
  const ends_on = saturdayOf(input.ends_on);
  if (starts_on === input.starts_on && ends_on === input.ends_on) return input;
  return {
    ...input,
    starts_on,
    ends_on,
    build_from: input.starts_on,
    build_through: input.ends_on,
  };
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
function statsFor(
  schedule: Schedule,
  people: Record<string, CardPerson>,
): ShiftStats {
  const required = schedule.slots.reduce(
    (total, slot) => total + (slot.headcount || 0),
    0,
  );
  // Seats per cell, shadow shifts excluded — `audit._coverage`'s arithmetic,
  // since these tiles sit beside the ones that panel renders and two numbers
  // for one week is worse than one week with no numbers.
  const seats = new Map<string, number>();
  for (const row of schedule.assignments) {
    if (people[row.employee]?.counts_toward_staffing === false) continue;
    const at = `${row.shift}|${row.date}`;
    seats.set(at, (seats.get(at) ?? 0) + 1);
  }

  let assigned = 0;
  let unfilled = 0;
  for (const slot of schedule.slots) {
    const filled = seats.get(`${slot.shift_name}|${slot.slot_date}`) ?? 0;
    const needed = slot.headcount || 0;
    // Capped: three people on a one-person shift is one place covered and two
    // overstaffed, not three places filled. Uncapped, an overstaffed Sunday
    // paid for an unstaffed Monday and the week read as fully covered.
    assigned += Math.min(filled, needed);
    if (filled < needed) unfilled += 1;
  }

  return {
    ...EMPTY_STATS,
    total_shifts: schedule.assignments.length,
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
  total_nights: 0,
  people_working: 0,
  coverage: { required: 0, assigned: 0, unfilled_slots: 0, percent: 100 },
  by_shift: [],
  by_day: [],
  by_employee: [],
  warning_counts: [],
  conflicts: 0,
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
  dates,
  weekStart,
  weekEnd,
}: {
  /** The columns the grid will have: a week's seven, or a day view's one. */
  dates: string[];
  weekStart: string;
  weekEnd: string;
}) {
  return (
    <div className="board-loading" role="status" aria-busy="true">
      <p className="board-loading-line">
        <LoaderCircle className="spin" size={16} aria-hidden="true" />
        טוען את השיבוצים לשבוע…
      </p>

      {/* Marked hidden from assistive tech: the line above already says
          what is happening, and a screen reader walking twenty-one empty
          placeholder cells is noise, not information. */}
      <div
        className={`board-loading-grid${dates.length === 1 ? " is-day" : ""}`}
        aria-hidden="true"
      >
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
  span = false,
}: {
  message: string;
  onRetry: () => void;
  /** The read that failed was a two-week or month span, not one week. */
  span?: boolean;
}) {
  return (
    <div className="board-empty board-load-error" role="alert">
      <h2>
        <AlertTriangle size={18} aria-hidden="true" />
        לא הצלחנו לטעון את הסידור
      </h2>
      <p>
        {span
          ? "התאריכים האלה לא נקראו מהשרת, כך שאיננו יודעים אם יש בהם סידור."
          : "השבוע הזה לא נקרא מהשרת, כך שאיננו יודעים אם יש בו סידור."}{" "}
        אפשר לנסות שוב — שום דבר לא נכתב ולא נמחק.
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
  fromDay,
  onGenerate,
  onOpenBlank,
}: {
  busy: boolean;
  generating: boolean;
  profile: WorkplaceProfile | null;
  weekStart: string;
  weekEnd: string;
  /** The day a build of the rest of the week would start on, or empty when
   *  there is none to offer. */
  fromDay: string;
  /** Open the build dialog on the whole week, or from one day of it. */
  onGenerate: (from?: string) => void;
  onOpenBlank: () => void;
}) {
  if (!profile) {
    return (
      <div className="board-empty">
        <h2>צריך להשלים את הגדרת היחידה</h2>
        <p>
          הגדרת היחידה מספקת את המשמרות, העובדים והכללים. בלעדיה אין ממה לבנות
          סידור — גם לא ידנית, כי סוגי המשמרות עדיין אינם מוגדרים.
        </p>
      </div>
    );
  }

  // A profile exists but setup is incomplete. The distinction that
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
          בלי סוגי משמרות אין שורות שמהן אפשר לבנות לוח — גם לא ידנית. פתחו
          את הגדרת היחידה מהכפתור בסרגל העליון והשלימו אותן.
        </p>
      </div>
    );
  }

  return (
    <div className="board-empty" data-tour="empty-week">
      <h2>אין סידור לשבוע הזה</h2>
      <p>
        אפשר לבקש מהסוכן לבנות את השבוע, או לפתוח שבוע ריק ולשבץ ידנית — בלי
        הסוכן בכלל.
      </p>
      {gaps && !gaps.complete ? (
        <p className="board-empty-partial">
          פרופיל היחידה עדיין חלקי, כך שהסוכן בונה על סמך המידע שנשמר. אפשר
          להשלים אותו בהגדרת היחידה או לשאול את הסוכן מה חסר.
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
        {/* The rest of the week, from the day the manager is on. Not
            offered from a Sunday, where it is the week and the button beside
            it already says so. The end is a default: the dialog it opens
            takes any other day. */}
        {fromDay && fromDay !== weekStart ? (
          <button
            type="button"
            className="ghost-button"
            onClick={() => onGenerate(fromDay)}
            disabled={busy || generating}
            title="בניית הסידור מהיום הזה עד שבת, או עד תאריך שתבחרו"
          >
            <CalendarPlus size={14} />
            {fromDay === weekEnd
              ? "בנייה ליום שבת בלבד"
              : `בנייה מיום ${hebrewWeekday(fromDay)} עד שבת`}
          </button>
        ) : null}
        <button
          type="button"
          className="primary-button"
          onClick={() => onGenerate()}
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
