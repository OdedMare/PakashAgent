"use client";

import {
  AlertTriangle,
  CalendarPlus,
  PencilLine,
  RefreshCw,
  Upload,
} from "lucide-react";

import type { WorkplaceProfile } from "@/types";
import { CrewStage } from "@/components/Crew";
import { displayDate } from "@/components/DateInput";
import { hebrewWeekday } from "@/components/Management/Calendar";


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
export function BoardLoading({
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
      <CrewStage label="טוען את השיבוצים לשבוע…" />

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
export function BoardLoadError({
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
export function EmptyWeek({
  busy,
  generating,
  profile,
  weekStart,
  weekEnd,
  fromDay,
  onGenerate,
  onOpenBlank,
  onImport,
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
  onImport?: () => void;
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
        אפשר לבקש מהסוכן לבנות את השבוע, לפתוח שבוע ריק ולשבץ ידנית — בלי
        הסוכן בכלל — או לייבא סידור שכבר קיים אצלכם בקובץ.
      </p>
      {gaps && !gaps.complete ? (
        <p className="board-empty-partial">
          פרופיל היחידה עדיין חלקי, כך שהסוכן בונה על סמך המידע שנשמר. אפשר
          להשלים אותו בהגדרת היחידה או לשאול את הסוכן מה חסר.
        </p>
      ) : null}
      <div className="board-empty-actions">
        {/* A week the workplace already has in a file, in whatever shape.
            The import screen reads and shows; only its confirm stores (D7). */}
        {onImport ? (
          <button
            type="button"
            className="ghost-button"
            onClick={onImport}
            disabled={busy || generating}
            title="ייבוא סידור קיים מקובץ Excel, CSV או Word"
          >
            <Upload size={14} />
            ייבוא מקובץ
          </button>
        ) : null}
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
