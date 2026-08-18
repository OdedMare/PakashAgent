"use client";

import {
  AlertCircle,
  CalendarDays,
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
import type { Assignment, TeamView } from "@/types";

import { AgentChat } from "./AgentChat";
import { Calendar, formatDate } from "./Calendar";
import { ConfirmMove } from "./ConfirmMove";
import { History } from "./History";
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
            </>
          ) : (
            <EmptyState busy={state.busy} hasProfile={Boolean(overview?.profile)} />
          )}

          <History entries={overview?.changes ?? []} />
        </div>

        <div className="management-side">
          <AgentChat
            proposal={state.proposal}
            busy={state.busy}
            onPropose={state.propose}
            onConfirm={state.confirm}
            onDismiss={state.dismissProposal}
          />
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
