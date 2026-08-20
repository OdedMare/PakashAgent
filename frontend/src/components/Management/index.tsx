"use client";

import {
  AlertCircle,
  CalendarDays,
  Download,
  Eye,
  EyeOff,
  LogOut,
  LayoutGrid,
  Moon,
  MessagesSquare,
  PencilLine,
  Settings2,
  Share2,
  Upload,
  Sparkles,
  Sun,
  Users,
} from "lucide-react";
import { useState } from "react";

import { Board } from "@/components/Board";
import { useTheme } from "@/components/Interview/useTheme";
import { SettingsPanel } from "@/components/Settings";
import { ShareLink } from "@/components/Workspace/ShareLink";
import type { Assignment, ShiftStats, TeamView } from "@/types";

import { AgentAnswer } from "./AgentAnswer";
import { AgentChat } from "./AgentChat";
import { Briefing } from "./Briefing";
import { Calendar, formatDate } from "./Calendar";
import { ConfirmMove } from "./ConfirmMove";
import { History } from "./History";
import { LearnedFromChanges } from "./LearnedFromChanges";
import { ImportSchedule } from "./ImportSchedule";
import { Preferences } from "./Preferences";
import { RequestInbox } from "./RequestInbox";
import { SimulationPanel } from "./SimulationPanel";
import { SwapInbox } from "./SwapInbox";
import { Stats } from "./Stats";
import { TeamPanel } from "./TeamPanel";
import { Warnings } from "./Warnings";
import { useManagement } from "./useManagement";

/** The manager's control room, opened once the intro interview is done.
 *
 *  **Two surfaces over one state.** `useManagement` is called once here and
 *  both views render from it, so a shift moved on the board and a shift
 *  moved by talking to the agent are the same write against the same
 *  refetched world — there is no second copy of the schedule to drift.
 *
 *  - **The board is what opens.** It is the manager's operational home: the
 *    week they are in, its coverage, and every gesture for editing it. It
 *    needs no model for any of that.
 *  - **The control room is one click away**, unchanged: the conversation
 *    with the agent, its briefing, the roster and its constraints, the
 *    request and swap inboxes, the change log, the import screen and the
 *    stats. This is where the *agent* lives, and the agent is the product —
 *    the board just does not make you go through it to move a shift.
 *
 *  Both are always reachable from the same switch in the header, in the same
 *  place, so neither is a mode the manager can get stranded in.
 *
 *  The decisions shaping every interaction are unchanged on both:
 *
 *  - **Changes are proposed, then confirmed.** Whether the manager drags a
 *    shift or types a sentence, the same two steps run and the same two
 *    reasons get recorded (D8). The drag is a nicer way to say what you want,
 *    not a way around saying why.
 *  - **Warnings inform, never block** (D3). The publish button is live
 *    regardless of what the audit found. */
export function Management({
  workspace,
  busy: workspaceBusy = false,
  onLogout,
  onRotateLink,
  onOpenInterview,
}: {
  workspace: TeamView;
  busy?: boolean;
  onLogout?: () => void;
  onRotateLink?: () => void;
  onOpenInterview?: () => void;
}) {
  const state = useManagement();
  const { theme, toggle } = useTheme();
  // Which surface is showing. The board is the default because it is the
  // operational home screen (and the one that works with no model); the
  // control room is where the manager goes to talk to the agent about what
  // they are looking at.
  const [view, setView] = useState<"board" | "room">("board");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [shareOpen, setShareOpen] = useState(false);
  // The import flow. Opening it writes nothing; the screen's own confirm
  // button is what persists (D7).
  const [importOpen, setImportOpen] = useState(false);
  // A drop parks the intended move here and opens the confirmation. Nothing
  // has been sent to the server at this point — the dialog is what writes.
  const [pendingMove, setPendingMove] = useState<{
    assignment: Assignment;
    shift_name: string;
    slot_date: string;
  } | null>(null);
  // A sentence the briefing offered, on its way to the composer. Held as a
  // counter alongside the text so clicking the same suggestion again re-seeds
  // the box after the manager has edited it.
  const [suggested, setSuggested] = useState<{ text: string; n: number }>({
    text: "",
    n: 0,
  });

  const overview = state.overview;
  // How many topics the interview left unsettled. Counted from the profile's
  // own record rather than re-derived, so the badge, the board's notice and
  // what the agent says when asked are all reading one answer. Zero — and no
  // badge — is the ordinary case: a confirmed interview carries no record at
  // all, because the gate refused to let it finish owing anything.
  const completeness = overview?.profile?.completeness;
  const openTopics =
    completeness && !completeness.complete
      ? completeness.missing_topics.length + completeness.open_points.length
      : 0;
  const schedule = overview?.schedule ?? null;
  // The roster in profile order. It is what the calendar assigns colours
  // from, so the order matters: position is the hue (see `palette.ts`).
  const roster = (overview?.employees ?? [])
    .map((row) => (typeof row.name === "string" ? row.name.trim() : ""))
    .filter((name) => name !== "");

  return (
    <div className="management">
      <header className="interview-header">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">
            <CalendarDays size={17} />
          </span>
          <span>
            {workspace.name}
            <span className="brand-sub"> · איזור ניהול</span>
          </span>
        </div>
        {/* The persistent navigation. Always in the header, always both
            entries, so neither surface is somewhere the manager can end up
            without a way back. */}
        <nav className="management-nav" aria-label="ניווט ראשי">
          <button
            type="button"
            className={`management-nav-item${view === "board" ? " is-active" : ""}`}
            onClick={() => setView("board")}
            aria-current={view === "board" ? "page" : undefined}
          >
            <LayoutGrid size={15} />
            לוח המשמרות
          </button>
          <button
            type="button"
            className={`management-nav-item${view === "room" ? " is-active" : ""}`}
            onClick={() => setView("room")}
            aria-current={view === "room" ? "page" : undefined}
          >
            <MessagesSquare size={15} />
            חדר הבקרה
          </button>
        </nav>

        <div className="header-actions">
          {onOpenInterview ? (
            <button
              type="button"
              className={
                openTopics ? "icon-button has-badge" : "icon-button"
              }
              onClick={onOpenInterview}
              aria-label={
                openTopics
                  ? `ראיון היכרות — ${openTopics} נושאים פתוחים`
                  : "ראיון היכרות"
              }
              title={
                openTopics
                  ? `הראיון לא הושלם — ${openTopics} נושאים עוד לא סוכמו`
                  : "ראיון היכרות"
              }
            >
              <Sparkles size={17} />
              {openTopics ? (
                <span className="icon-badge" aria-hidden="true">
                  {openTopics > 9 ? "9+" : openTopics}
                </span>
              ) : null}
            </button>
          ) : null}
          {workspace.member_token ? (
            <button
              type="button"
              className="icon-button"
              onClick={() => setShareOpen((open) => !open)}
              aria-label="קישור לצוות"
              title="קישור לצוות"
              aria-expanded={shareOpen}
            >
              <Share2 size={17} />
            </button>
          ) : null}
          <button
            type="button"
            className="icon-button"
            onClick={() => setSettingsOpen(true)}
            aria-label="הגדרות מערכת"
            title="הגדרות מערכת"
          >
            <Settings2 size={17} />
          </button>
          <button
            type="button"
            className="icon-button"
            onClick={toggle}
            aria-label={theme === "dark" ? "מצב בהיר" : "מצב כהה"}
          >
            {theme === "dark" ? <Sun size={17} /> : <Moon size={17} />}
          </button>
          {onLogout ? (
            <button
              type="button"
              className="icon-button"
              onClick={onLogout}
              aria-label="יציאה"
              title="יציאה"
            >
              <LogOut size={17} />
            </button>
          ) : null}
        </div>
      </header>

      {shareOpen && workspace.member_token ? (
        <ShareLink
          token={workspace.member_token}
          busy={workspaceBusy}
          onRotate={() => onRotateLink?.()}
        />
      ) : null}

      {state.error ? (
        <div className="error" role="alert">
          <AlertCircle size={16} />
          <span>{state.error}</span>
          <button type="button" onClick={state.clearError}>
            סגירה
          </button>
        </div>
      ) : null}

      {/* The board: the manager's home screen. Renders from the same
          `useManagement` state the control room does, so a write from
          either lands in one place and both re-read together. */}
      {view === "board" ? (
        <Board
          overview={overview}
          busy={state.busy}
          dark={theme === "dark"}
          onGenerate={state.generate}
          onOpenBlank={state.openBlank}
          onAssign={state.assign}
          onUnassign={state.unassign}
          onMove={state.move}
          onPublish={state.publish}
          onExport={state.exportSchedule}
          onOpenAgent={() => setView("room")}
        />
      ) : null}

      <main
        className="management-body"
        hidden={view !== "room"}
      >
        <div className="management-main">
          <div className="management-toolbar">
            <div className="period">
              {schedule ? (
                <>
                  <span className="period-range">
                    {formatDate(schedule.starts_on)} –{" "}
                    {formatDate(schedule.ends_on)}
                  </span>
                  <span
                    className={`period-status is-${schedule.status}`}
                  >
                    {schedule.status === "published" ? "פורסם" : "טיוטה"}
                  </span>
                </>
              ) : (
                <span className="period-range">אין סידור פעיל</span>
              )}
            </div>

            <div className="toolbar-actions">
              {/* The other direction of D6: a schedule the workplace already
                  had, absorbed rather than retyped. Always available, not
                  only when a period exists — an import is usually the first
                  thing a new workspace does. */}
              <button
                type="button"
                className="ghost-button"
                onClick={() => setImportOpen(true)}
                disabled={state.busy}
                title="טעינת סידור קיים מאקסל או וורד"
              >
                <Upload size={14} />
                טעינת סידור
              </button>
              {/* The copy that leaves the app (D17). Laid out shift-major
                  like the real source files, so a week can be edited in
                  Excel and imported back rather than only looked at. */}
              {schedule ? (
                <button
                  type="button"
                  className="ghost-button"
                  onClick={() => state.exportSchedule(schedule.id)}
                  disabled={state.busy}
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
                    state.publish(
                      schedule.id,
                      schedule.status !== "published",
                    )
                  }
                  disabled={state.busy}
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
              {/* The authoring half of D6, which until now had no button.
                  Placed beside "generate" rather than hidden behind it:
                  they are two equal ways to start a week, and this one
                  calls no model at all. */}
              <button
                type="button"
                className="ghost-button"
                onClick={() => state.openBlank({})}
                disabled={state.busy}
                title="פתיחת שבוע ריק לשיבוץ ידני, בלי הסוכן"
              >
                <PencilLine size={14} />
                סידור ריק
              </button>
              <button
                type="button"
                className="primary-button"
                onClick={() => state.generate({})}
                disabled={state.busy}
              >
                {state.busy ? "בונה…" : "בניית סידור לשבוע"}
              </button>
            </div>
          </div>

          {schedule ? (
            <>
              <Calendar
                schedule={schedule}
                constraints={overview?.availability ?? []}
                employees={roster}
                dark={theme === "dark"}
                onDrop={setPendingMove}
                onAssign={state.assign}
                onUnassign={(assignment) =>
                  state.unassign({ assignment_id: assignment.id })
                }
              />
              {schedule.notes?.length ? (
                <ul className="schedule-notes">
                  {schedule.notes.map((note, index) => (
                    <li key={index}>{note}</li>
                  ))}
                </ul>
              ) : null}
              <Warnings warnings={schedule.warnings} />
              {/* The same period the calendar above shows, counted. Placed
                  under the warnings rather than over the grid: the schedule
                  is what the manager opened this screen for, and the figures
                  are what they turn to once they have looked at it. Both are
                  the audit's arithmetic, so the panel and the warnings can
                  never disagree. */}
              <Stats stats={overview?.stats ?? EMPTY_STATS} />
            </>
          ) : (
            <EmptyState busy={state.busy} hasProfile={Boolean(overview?.profile)} />
          )}

          {/* Beneath the log it is derived from: the entries are what
              happened, and this is what they may add up to. Proposals
              only — nothing here is a rule until the manager makes it
              one (D7). */}
          <History entries={overview?.changes ?? []} />
          <LearnedFromChanges />
        </div>

        <div className="management-side">
          {/* The agent's own initiative, above the conversation because it is
              what it said before being asked (D15). It proposes nothing and
              applies nothing — clicking a suggestion types it into the
              composer below and the manager still sends it. */}
          <Briefing
            briefing={state.briefing}
            busy={state.briefing_busy}
            onAsk={(text) =>
              setSuggested((previous) => ({ text, n: previous.n + 1 }))
            }
            onDismiss={state.dismissBriefing}
          />
          {/* What the agent found when *asked*. A fifth card state, distinct
              from the proposal below it: an answer carries no operations and
              has no confirm button, because reading the schedule is not the
              same act as changing it. */}
          <AgentAnswer
            answer={state.answer}
            busy={state.answer_busy}
            onDismiss={state.dismissAnswer}
          />
          {/* A change being considered rather than requested. Rendered in
              its own colour above the proposal so the two can never be
              confused — nothing here has been written, and approving runs
              the ordinary apply path with the manager's reason (D8). */}
          <SimulationPanel
            simulation={state.simulation}
            busy={state.busy}
            onApprove={state.approveSimulation}
            onDiscard={state.dismissSimulation}
          />
          <AgentChat
            proposal={state.proposal}
            busy={state.busy}
            draft={suggested.text}
            draftKey={suggested.n}
            onPropose={state.propose}
            onAsk={state.ask}
            onSimulate={state.simulate}
            onConfirm={state.confirm}
            onDismiss={state.dismissProposal}
          />
          {/* Employee submissions awaiting a ruling (D14). Above the team
              panel because a pending request is a thing to act on, while the
              panel below it is reference. */}
          <RequestInbox onDecided={state.refresh} />
          {/* Beside the constraint inbox, not merged into it: one
              records a fact and the other moves two assignments, so
              they carry different requirements at the button. */}
          <SwapInbox onDecided={state.refresh} />
          {/* What the workplace has taught the agent. Beside the roster
              because both are reference the agent reads before it proposes —
              and everything in it is visible and editable, because a stored
              preference the manager cannot see is a rule they never agreed
              to. */}
          <Preferences busy={state.busy} />
          <TeamPanel
            employees={overview?.employees ?? []}
            shifts={overview?.shifts ?? []}
            constraints={overview?.availability ?? []}
            onAdd={state.addConstraint}
            onRemove={state.removeConstraint}
          />
        </div>
      </main>

      {/* The drag proposed a move; this is what actually applies it, and only
          once the manager has said why (D8). */}
      {pendingMove ? (
        <ConfirmMove
          assignment={pendingMove.assignment}
          shiftName={pendingMove.shift_name}
          slotDate={pendingMove.slot_date}
          busy={state.busy}
          onCancel={() => setPendingMove(null)}
          onConfirm={(reason) => {
            state.move({
              assignment_id: pendingMove.assignment.id,
              shift_name: pendingMove.shift_name,
              slot_date: pendingMove.slot_date,
              reason,
            });
            setPendingMove(null);
          }}
        />
      ) : null}

      {/* Reading the files writes nothing; this screen's own confirm button
          is the only thing that persists (D7). */}
      {importOpen ? (
        <ImportSchedule
          shiftNames={(overview?.shifts ?? [])
            .map((shift) => String((shift as { name?: unknown }).name ?? ""))
            .filter(Boolean)}
          onClose={() => setImportOpen(false)}
          onImported={() => {
            setImportOpen(false);
            void state.refresh();
          }}
        />
      ) : null}

      {settingsOpen ? (
        <SettingsPanel onClose={() => setSettingsOpen(false)} />
      ) : null}
    </div>
  );
}

/** Zeros, for the moment before the first overview lands.
 *
 *  The backend sends a well-formed `stats` on every overview, including for
 *  a team with no schedule at all — this exists only so the panel has a
 *  shape during the first fetch, and it renders nothing from it. */
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

/** Before the first schedule exists.
 *
 *  Says which of the two situations this is — no profile yet, or a profile
 *  with nothing built from it — because the action differs and a generic
 *  empty state would leave the manager guessing. */
function EmptyState({
  busy,
  hasProfile,
}: {
  busy: boolean;
  hasProfile: boolean;
}) {
  return (
    <div className="center management-empty">
      <span className="brand-mark" aria-hidden="true">
        <Users size={17} />
      </span>
      <h1>{hasProfile ? "עוד לא נבנה סידור" : "צריך להשלים את הראיון"}</h1>
      <p>
        {hasProfile
          ? "אפשר לבקש מהסוכן לבנות סידור לשבוע הקרוב, או לפתוח שבוע ריק ולשבץ בעצמך. בשני המקרים אפשר להזיז משמרות ולדבר עם הסוכן על השיבוץ."
          : "ראיון ההיכרות הוא מה שמלמד את הסוכן את המשמרות, העובדים והכללים. בלעדיו אין ממה לבנות סידור — גם לא ידנית, כי המשמרות עצמן מגיעות משם."}
      </p>
      {busy ? <p className="management-empty-busy">בונה סידור…</p> : null}
    </div>
  );
}
