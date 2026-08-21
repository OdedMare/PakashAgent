"use client";

import { MessagesSquare, TriangleAlert, X } from "lucide-react";

import type { ProfileGaps } from "./useManagement";

/** A refused build, rendered as a fork rather than a failure.
 *
 *  The backend refuses to build a week over a profile with no shift
 *  vocabulary — D9 forbids inventing shift names, so there is genuinely no
 *  grid to make. That refusal used to arrive as a bare 502 and the manager
 *  had nowhere to go from it: both buttons failed, the message named no
 *  cause, and the interview that could fix it was behind an icon they had no
 *  reason to press.
 *
 *  So this names the gap and offers the two ways to close it, which are
 *  genuinely different acts:
 *
 *  - **The interview** is where a profile is written. It is the only thing
 *    that writes one, which is why it is the primary action here.
 *  - **The agent** can be asked about the week without writing anything
 *    (D15). It reads the same `completeness` record this panel renders, so a
 *    manager who wants to work out *what* is missing before answering for it
 *    has somewhere to think out loud.
 *
 *  Deliberately not a red error box. Nothing broke — the interview is
 *  unfinished, and styling that as a fault would tell the manager they hit a
 *  bug when they hit a step they skipped. */
export function ProfileGapsNotice({
  gaps,
  onOpenInterview,
  onDiscuss,
  onDismiss,
}: {
  gaps: ProfileGaps;
  /** Opens the intro interview. Absent when the host screen has no route to
   *  it, in which case the panel simply omits the button rather than
   *  offering one that goes nowhere. */
  onOpenInterview?: () => void;
  /** Seeds the control room's composer with a question about this week and
   *  switches to it. Seeded, never sent: the manager presses send, the same
   *  rule every other agent suggestion follows (D15). */
  onDiscuss: () => void;
  onDismiss: () => void;
}) {
  return (
    <section className="gaps-notice" aria-live="polite">
      <div className="gaps-head">
        <TriangleAlert size={16} aria-hidden="true" />
        <p>{gaps.message}</p>
        <button
          type="button"
          className="icon-button"
          onClick={onDismiss}
          aria-label="סגירה"
        >
          <X size={14} />
        </button>
      </div>

      {/* What the interview still owes, in its own words. Listed rather than
          summarised into a count: the manager is about to go and answer
          these, and a number tells them nothing about what to say. */}
      {gaps.gaps.length ? (
        <ul className="gaps-list">
          {gaps.gaps.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      ) : null}

      {/* What each gap costs. Separate from the list above because "no shift
          types" and "so there is no board to build" are a fact and its
          consequence, and the consequence is the part that explains why the
          button did nothing. */}
      {gaps.blocks.length ? (
        <ul className="gaps-blocks">
          {gaps.blocks.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      ) : null}

      <div className="gaps-actions">
        {onOpenInterview ? (
          <button
            type="button"
            className="primary-button"
            onClick={onOpenInterview}
          >
            השלמת ראיון ההיכרות
          </button>
        ) : null}
        <button type="button" className="ghost-button" onClick={onDiscuss}>
          <MessagesSquare size={14} />
          דיון עם הסוכן על השבוע
        </button>
      </div>
    </section>
  );
}
