"use client";

import {
  AlertCircle,
  CalendarDays,
  CircleAlert,
  FlagTriangleRight,
  LayoutGrid,
  LogOut,
  MessagesSquare,
  Moon,
  Plus,
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
}: {
  workspace?: TeamView;
  busy?: boolean;
  onLogout?: () => void;
  onRotateLink?: () => void;
  /** Leave the interview for the management area. Supplied only when there
   *  is one to go back to — a workplace already taught — so a first-time
   *  interview has no exit that would strand the manager without a profile. */
  onDone?: () => void;
} = {}) {
  const {
    turn, busy, error, blocked, start, answer, finish, extend, reset, retry,
  } = useInterview();
  const { theme, toggle } = useTheme();
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [shareOpen, setShareOpen] = useState(false);
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
                gaps={blocked ? turn.gaps : []}
              />
            ) : null}
          </>
        ) : (
          <Welcome
            busy={busy}
            taught={Boolean(workspace?.profile)}
            onStart={start}
            onContinue={extend}
          />
        )}
      </main>

      {/* The refusal to stop, stated once above the composer. `blocked` is
          what raises it — the same list rides on every turn, and showing it
          on the second question of a twenty-one-question interview would
          read as a complaint about one that has barely started. */}
      {turn && !complete && blocked && turn.gaps.length > 0 ? (
        <div className="gaps-notice" role="status">
          <CircleAlert size={16} />
          <div>
            <strong>עוד לא ניתן לבנות סידור מהמידע שנאסף.</strong>
            <ul>
              {turn.gaps.map((gap) => (
                <li key={gap}>{gap}</li>
              ))}
            </ul>
            <span>נסגור את זה ואפשר יהיה לשבץ — כל השאר יכול לחכות.</span>
          </div>
        </div>
      ) : null}

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
        <>
          <Composer disabled={busy} onSend={answer} />
          {/* The way out of the topic list. Twenty-one topics is the
              thorough version of this conversation, not the only one — a
              manager who wants a schedule this afternoon stops here, and
              whether that is possible yet is the server's answer, not this
              button's. */}
          <div className="interview-finish">
            <button
              type="button"
              className="ghost-button"
              onClick={finish}
              disabled={busy}
              title="סיום הראיון ומעבר לשיבוץ עם המידע שנאסף עד כה"
            >
              <FlagTriangleRight size={14} />
              סיום ומעבר לשיבוץ
            </button>
            <span>אפשר להשלים פרטים גם אחר כך.</span>
          </div>
        </>
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
            onClick={() => (onDone ? onDone() : window.location.reload())}
          >
            מעבר לאיזור הניהול
          </button>
          {/* The profile is the last thing the manager agreed to, never a
              final answer. This continues the same conversation rather than
              starting a second one, so the agent still knows everything
              already settled and only what is new gets asked. */}
          <button
            type="button"
            className="ghost-button"
            onClick={extend}
            disabled={busy}
            title="חזרה לראיון כדי להוסיף מידע על מקום העבודה"
          >
            <Plus size={14} />
            השלמת מידע נוסף
          </button>
        </div>
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

      {busy ? (
        <div className="turn assistant">
          <div className="avatar" aria-hidden="true">
            פ
          </div>
          <div className="turn-body">
            <div className="thinking" role="status" aria-label="הסוכן חושב">
              <span />
              <span />
              <span />
            </div>
          </div>
        </div>
      ) : null}

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

/** The opening screen.
 *
 *  `taught` means this workspace already has a profile, which changes what
 *  the button should do: continuing the interview it already had keeps
 *  everything settled and asks only what is new, while starting over asks
 *  for all of it again and replaces the profile everything downstream reads.
 *  Reached this way only when the browser has no session id to resume —
 *  a second machine, or cleared storage. */
function Welcome({
  busy,
  taught,
  onStart,
  onContinue,
}: {
  busy: boolean;
  taught: boolean;
  onStart: () => void;
  onContinue: () => void;
}) {
  return (
    <div className="center">
      <span className="brand-mark" aria-hidden="true">
        <MessagesSquare size={17} />
      </span>
      <h1>{taught ? "נמשיך מאיפה שהפסקנו" : "נעים להכיר"}</h1>
      <p>
        {taught
          ? "כבר הכרתי את מקום העבודה שלכם. אפשר להמשיך את אותה שיחה ולהוסיף מה שחסר, או להתחיל ראיון חדש — ראיון חדש מחליף את הפרופיל הקיים."
          : "לפני שאפשר לבנות סידור, כדאי שאכיר את מקום העבודה: המשמרות, העובדים והכללים שלכם. זה ראיון קצר — שאלה אחת בכל פעם, ואפשר לבחור תשובה או לכתוב משלכם."}
      </p>
      <button
        type="button"
        className="start-button"
        onClick={taught ? onContinue : onStart}
        disabled={busy}
      >
        {busy ? "רגע…" : taught ? "המשך הראיון" : "בואו נתחיל"}
      </button>
      {taught ? (
        <button
          type="button"
          className="ghost-button"
          onClick={onStart}
          disabled={busy}
        >
          <RotateCcw size={14} />
          ראיון חדש מההתחלה
        </button>
      ) : null}
    </div>
  );
}
