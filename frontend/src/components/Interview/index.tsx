"use client";

import {
  AlertCircle,
  CalendarDays,
  DoorOpen,
  LayoutGrid,
  LogOut,
  MessagesSquare,
  Moon,
  RotateCcw,
  Settings2,
  Share2,
  Sun,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { SettingsPanel } from "@/components/Settings";
import { ShareLink } from "@/components/Workspace/ShareLink";
import type { TeamView } from "@/types";

import { Composer } from "./Composer";
import { ConfirmEnd } from "./ConfirmEnd";
import { DraftPanel } from "./DraftPanel";
import { ProfileSummary } from "./ProfileSummary";
import { Turn } from "./Turn";
import { useInterview } from "./useInterview";
import { useTheme } from "./useTheme";

/** Roughly the topic count in `bl/interview.py`. Used only as a floor for
 *  the denominator early on, when the agent has resolved two points and
 *  raised one — without it, the bar would read 66% on the second turn. */
const EXPECTED_TOPICS = 21;

/** The boss's surface: the intro interview plus the workspace controls.
 *
 *  `workspace` is optional so the component still renders standalone in a
 *  test or a storybook; in the app it always arrives, supplied by the
 *  `Workspace` router after the server has confirmed the boss role. */
export function Interview({
  workspace,
  busy: workspaceBusy = false,
  onLogout,
  onRotateLink,
  onDone,
  onBuild,
}: {
  workspace?: TeamView;
  busy?: boolean;
  onLogout?: () => void;
  onRotateLink?: () => void;
  /** Leave the interview for the management area.
   *
   *  Supplied whether or not a profile already exists. It used to be
   *  withheld on a first interview so nobody could arrive at the management
   *  area with nothing to schedule against — but that made the first
   *  interview a room with no door, which is worse: a manager who runs out
   *  of time has to abandon the app rather than the conversation. Ending
   *  early writes a partial profile instead, and the board says what is
   *  missing. */
  onDone?: () => void;
  /** Open the shift board and generate its first schedule. */
  onBuild?: () => void;
} = {}) {
  const { turn, busy, error, start, answer, end, reset, retry } =
    useInterview();
  const { theme, toggle } = useTheme();
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [shareOpen, setShareOpen] = useState(false);
  // The confirmation in front of ending early. Closing writes the profile
  // the whole management area reads, so it is not something a mis-click
  // should do — but it is also not a decision worth a whole screen.
  const [endingOpen, setEndingOpen] = useState(false);

  /** Close the interview, then leave for the management area.
   *
   *  Sequenced rather than fired together: the management area renders from
   *  `workspace.profile`, and that profile is what `end` writes. Navigating
   *  first would race the write and land back on the interview. Reloading is
   *  the fallback when there is no router callback — it is what re-reads
   *  `/api/workspace/me`, whose `profile` is the switch. */
  const leave = async () => {
    await end();
    setEndingOpen(false);
    if (onDone) onDone();
    else window.location.reload();
  };
  const bottom = useRef<HTMLDivElement>(null);

  const complete = turn?.status === "complete";
  // The agent now reports its own state, so the bar tracks what it says is
  // settled against what it says remains — a far better signal than counting
  // turns, which credited a follow-up as progress and a folded answer as
  // none. Capped just short of full until the profile actually lands.
  const resolved = turn?.resolved.length ?? 0;
  const open = turn?.open_points.length ?? 0;
  const known = Math.max(resolved + open, EXPECTED_TOPICS);
  const progress = complete ? 100 : Math.min(94, (resolved / known) * 100);

  // Follow the conversation as it grows, including while a turn is being
  // generated — the thinking dots are the thing worth keeping in view.
  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turn?.turns.length, busy, complete]);

  return (
    <div className="interview">
      <header className="interview-header">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">
            <CalendarDays size={17} />
          </span>
          <span>
            {workspace ? workspace.name : "פקש"}
            <span className="brand-sub"> · ראיון היכרות</span>
          </span>
        </div>
        <div className="header-actions">
          {workspace?.member_token ? (
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
          {turn && !complete ? (
            <button
              type="button"
              className="icon-button"
              onClick={() => setEndingOpen(true)}
              aria-label="סיום הראיון"
              title="סיום הראיון ומעבר לאיזור הניהול"
            >
              <DoorOpen size={17} />
            </button>
          ) : null}
          {turn ? (
            <button
              type="button"
              className="icon-button"
              onClick={reset}
              aria-label="ראיון חדש"
              title="ראיון חדש"
            >
              <RotateCcw size={17} />
            </button>
          ) : null}
          {onDone ? (
            <button
              type="button"
              className="icon-button"
              onClick={onDone}
              aria-label="חזרה לאיזור הניהול"
              title="חזרה לאיזור הניהול"
            >
              <LayoutGrid size={17} />
            </button>
          ) : null}
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

      {shareOpen && workspace?.member_token ? (
        <ShareLink
          token={workspace.member_token}
          busy={workspaceBusy}
          onRotate={() => onRotateLink?.()}
        />
      ) : null}

      {turn ? (
        <div
          className="progress"
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={Math.round(progress)}
          aria-label="התקדמות הראיון"
        >
          <div className="progress-fill" style={{ width: `${progress}%` }} />
        </div>
      ) : null}

      <main id="interview" className={turn && !complete ? "with-draft" : ""}>
        {turn ? (
          <>
            <Thread
              turn={turn}
              busy={busy}
              complete={complete}
              onSelect={answer}
              bottomRef={bottom}
            />
            {!complete ? (
              <DraftPanel
                draft={turn.draft}
                resolved={turn.resolved}
                openPoints={turn.open_points}
                busy={busy}
              />
            ) : null}
          </>
        ) : (
          <Welcome busy={busy} onStart={start} />
        )}
      </main>

      {error ? (
        <div className="error" role="alert">
          <AlertCircle size={16} />
          <span>{error}</span>
          <button type="button" onClick={retry}>
            נסו שוב
          </button>
        </div>
      ) : null}

      {turn && !complete ? (
        <Composer disabled={busy} onSend={answer} />
      ) : null}

      {/* The interview's result is the profile the management area runs on,
          so finishing it hands the manager straight to that area rather than
          leaving them on a summary screen. Reloading is what re-reads
          `/api/workspace/me`, whose `profile` is the switch. */}
      {complete ? (
        <div className="interview-done">
          <button
            type="button"
            className="primary-button"
            onClick={() =>
              onBuild ? onBuild() : onDone ? onDone() : window.location.reload()
            }
          >
            בניית סידור המשמרות שלנו
          </button>
        </div>
      ) : null}

      {endingOpen && turn ? (
        <ConfirmEnd
          draft={turn.draft}
          openPoints={turn.open_points}
          busy={busy}
          onConfirm={leave}
          onCancel={() => setEndingOpen(false)}
        />
      ) : null}

      {settingsOpen ? (
        <SettingsPanel onClose={() => setSettingsOpen(false)} />
      ) : null}
    </div>
  );
}

function Thread({
  turn,
  busy,
  complete,
  onSelect,
  bottomRef,
}: {
  turn: NonNullable<ReturnType<typeof useInterview>["turn"]>;
  busy: boolean;
  complete: boolean;
  onSelect: (answer: string) => void;
  bottomRef: React.Ref<HTMLDivElement>;
}) {
  // Only the final assistant turn may be answered, and only while nothing is
  // in flight — otherwise a fast double-click sends two answers to the same
  // question and the model sees a contradiction it has to reconcile.
  const lastAssistant = turn.turns.reduce(
    (found, row, index) => (row.role === "assistant" ? index : found),
    -1,
  );

  return (
    <div className="thread">
      {turn.turns.map((message, index) => (
        <Turn
          key={index}
          message={message}
          live={!busy && !complete && index === lastAssistant}
          onSelect={onSelect}
        />
      ))}

      {busy ? <Thinking turn={turn} /> : null}

      {/* The draft is shown from the first turn, so the profile visibly fills
          in as the interview proceeds instead of appearing all at once at
          the end. Once complete, `profile` is the durable version. */}
      {complete && turn.profile ? (
        <ProfileSummary profile={turn.profile} />
      ) : null}

      <div ref={bottomRef} />
    </div>
  );
}

/** What the agent is doing while a turn is generated.
 *
 *  This replaced three anonymous dots. A turn is a whole model generation and
 *  can run for several seconds, during which the dots said only that
 *  something was happening — not that the answer had been received, not what
 *  was being worked on, and not that the wait was normal. The manager's own
 *  answer is echoed into the thread immediately, so the honest reading of
 *  this moment is "your answer is in, the agent is working through it", and
 *  that is what this says.
 *
 *  The phases are **elapsed-time labels, not a progress report**: nothing is
 *  streamed back mid-generation, so claiming to know the model is "now
 *  drafting the profile" would be an invention. They are ordered to match
 *  what a turn genuinely does — read the answer, update the draft, choose the
 *  next question — and the last one holds rather than cycling, because a
 *  label that loops forever reads as a hang.
 */
function Thinking({
  turn,
}: {
  turn: NonNullable<ReturnType<typeof useInterview>["turn"]>;
}) {
  const phase = useThinkingPhase();
  // Once there is a profile in progress the wait has a subject, so the label
  // names it instead of speaking in the abstract.
  const named = turn.draft?.workplace?.name;

  return (
    <div className="turn assistant">
      <div className="avatar" aria-hidden="true">
        פ
      </div>
      <div className="turn-body">
        <div className="thinking-row" role="status" aria-live="polite">
          <div className="thinking" aria-hidden="true">
            <span />
            <span />
            <span />
          </div>
          <span className="thinking-label">
            {phase}
            {named ? ` · ${named}` : ""}
          </span>
        </div>
      </div>
    </div>
  );
}

/** The three stages of a turn, advanced on a timer.
 *
 *  Deliberately not a spinner percentage: there is no progress to report, and
 *  a bar that fills at a rate unrelated to the work is a lie that gets caught
 *  the first time a turn takes twice as long. */
const THINKING_PHASES = [
  "קורא את התשובה",
  "מעדכן את הפרופיל",
  "מנסח את השאלה הבאה",
] as const;

function useThinkingPhase(): string {
  const [index, setIndex] = useState(0);

  // `Thinking` is mounted only while a turn is generating and unmounts when
  // it lands, so each wait gets a fresh hook and the phase starts at the
  // first label without needing to be reset.
  useEffect(() => {
    const timers = [
      window.setTimeout(() => setIndex(1), 1_600),
      window.setTimeout(() => setIndex(2), 4_000),
    ];
    return () => timers.forEach(window.clearTimeout);
  }, []);

  return THINKING_PHASES[index];
}


function Welcome({ busy, onStart }: { busy: boolean; onStart: () => void }) {
  return (
    <div className="center">
      <span className="brand-mark" aria-hidden="true">
        <MessagesSquare size={17} />
      </span>
      <h1>נעים להכיר</h1>
      <p>
        לפני שאפשר לבנות סידור, כדאי שאכיר את מקום העבודה: המשמרות, העובדים
        והכללים שלכם. זה ראיון קצר — שאלה אחת בכל פעם, ואפשר לבחור תשובה או
        לכתוב משלכם.
      </p>
      <button
        type="button"
        className="start-button"
        onClick={onStart}
        disabled={busy}
      >
        {busy ? "רגע…" : "בואו נתחיל"}
      </button>
    </div>
  );
}
