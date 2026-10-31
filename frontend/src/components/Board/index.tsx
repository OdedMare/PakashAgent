"use client";

import { EyeOff, LockKeyhole } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import type {
  AgentAnswer,
  Constraint,
  ManagementOverview,
  Proposal,
  RequiredAssignment,
  Schedule,
  Simulation,
} from "@/types";

import { collectTouches } from "./agentTouch";
import { BoardActions } from "./BoardActions";
import { BoardGrid } from "./BoardGrid";
import { ConfirmDrop } from "./ConfirmDrop";
import type { RemovalTarget } from "./ConfirmRemoval";
import { ConfirmRemoval } from "./ConfirmRemoval";
import { CoverageBar } from "./CoverageBar";
import { sundayOf } from "./dates";
import { FilterBar } from "./FilterBar";
import { GenerateDialog } from "./GenerateDialog";
import { RangeGrid } from "./RangeGrid";
import { orderByHours } from "./shiftOrder";
import { ShiftEditor } from "./ShiftEditor";
import { clipTo, mergePeriods } from "./span";
import { ViewSwitch } from "./ViewSwitch";
import { isOverview } from "./views";
import { WeekNav } from "./WeekNav";
import { WeekRail } from "./WeekRail";
import { addDays, useBoard, weekDates } from "./useBoard";
import { useBoardKeys } from "./useBoardKeys";
import { usePlacementDialogs } from "./usePlacementDialogs";
import { useRosterMaps } from "./useRosterMaps";
import { BoardLoading, BoardLoadError, EmptyWeek } from "./BoardStates";
import { covers, statsFor, EMPTY_STATS } from "./boardStats";
import { AgentTouchBar } from "./AgentTouchBar";

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
  onImport,
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
    /** Only these shift types are built; empty means every shift. */
    shifts?: string[];
    /** Absorb into the rows already there instead of rebuilding them. */
    keep_existing?: boolean;
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
    from_slot_id?: string;
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
  /** Open the import screen. Opening it writes nothing (D7). */
  onImport?: () => void;
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

  const { roster, roles, roleOptions, people } = useRosterMaps(overview);

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

  // What the manager has asked to remove, held until they confirm. Nothing
  // has reached the server while this is set — the same shape a drop has,
  // for a gesture that is even harder to take back.
  const [removal, setRemoval] = useState<RemovalTarget | null>(null);
  // The run the build dialog is open on, or null while it is closed.
  // `inPeriod` is fixed by where it was opened from — a day's column head,
  // or the card of a week with nothing stored — so a period landing
  // underneath an open dialog cannot change what its button will do.
  const [building, setBuilding] = useState<{
    from: string;
    through: string;
    inPeriod: boolean;
  } | null>(null);

  const {
    pendingMove, editor, setEditor, check, setCheck, checking,
    runCheck, openMove, closeDialogs,
  } = usePlacementDialogs(board.check, schedule?.id);

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

        <BoardActions
          period={period}
          busy={busy}
          writable={writable}
          touchCount={touches.size}
          onOpenAgent={onOpenAgent}
          onExport={onExport}
          onImport={onImport}
          onPublish={onPublish}
          onRemove={setRemoval}
        />
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
          onImport={onImport}
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
              from_slot_id: pendingMove.assignment.slot_id,
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
                    shifts: input.shifts,
                    keep_existing: input.keep_existing,
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
