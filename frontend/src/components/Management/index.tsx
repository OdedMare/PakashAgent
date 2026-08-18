"use client";

import {
  AlertCircle,
  CalendarDays,
  Download,
  Eye,
  EyeOff,
  LogOut,
  Moon,
  Settings2,
  Share2,
  Sparkles,
  Sun,
  Users,
} from "lucide-react";
import { useState } from "react";

import { useTheme } from "@/components/Interview/useTheme";
import { SettingsPanel } from "@/components/Settings";
import { ShareLink } from "@/components/Workspace/ShareLink";
import type { Assignment, ShiftStats, TeamView } from "@/types";

import { AgentChat } from "./AgentChat";
import { Briefing } from "./Briefing";
import { Calendar, formatDate } from "./Calendar";
import { ConfirmMove } from "./ConfirmMove";
import { History } from "./History";
import { RequestInbox } from "./RequestInbox";
import { Stats } from "./Stats";
import { TeamPanel } from "./TeamPanel";
import { Warnings } from "./Warnings";
import { useManagement } from "./useManagement";

/** The manager's control room, opened once the intro interview is done.
 *
 *  Holds the shift calendar, the roster and its constraints, and the
 *  conversation with the agent about the current and future schedule. The
 *  three are one screen on purpose: a change discussed in the chat lands on
 *  the calendar beside it, and the warnings under it update with both.
 *
 *  Two decisions shape every interaction here:
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
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [shareOpen, setShareOpen] = useState(false);
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
  const schedule = overview?.schedule ?? null;

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
        <div className="header-actions">
          {onOpenInterview ? (
            <button
              type="button"
              className="icon-button"
              onClick={onOpenInterview}
              aria-label="ראיון היכרות"
              title="ראיון היכרות"
            >
              <Sparkles size={17} />
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

      <main className="management-body">
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
                onDrop={setPendingMove}
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

          <History entries={overview?.changes ?? []} />
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
          <AgentChat
            proposal={state.proposal}
            busy={state.busy}
            draft={suggested.text}
            draftKey={suggested.n}
            onPropose={state.propose}
            onConfirm={state.confirm}
            onDismiss={state.dismissProposal}
          />
          {/* Employee submissions awaiting a ruling (D14). Above the team
              panel because a pending request is a thing to act on, while the
              panel below it is reference. */}
          <RequestInbox onDecided={state.refresh} />
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
          ? "אפשר לבקש מהסוכן לבנות סידור לשבוע הקרוב, ואז להזיז משמרות או לדבר איתו על השיבוץ."
          : "ראיון ההיכרות הוא מה שמלמד את הסוכן את המשמרות, העובדים והכללים. בלעדיו אין ממה לבנות סידור."}
      </p>
      {busy ? <p className="management-empty-busy">בונה סידור…</p> : null}
    </div>
  );
}
