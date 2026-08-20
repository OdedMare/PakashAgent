"use client";

import { DoorOpen, X } from "lucide-react";

import type { WorkplaceProfile } from "@/types";

/** The confirmation in front of ending the interview early.
 *
 *  Ending writes the profile the whole management area runs on, so it is not
 *  something a mis-click should do. But it is also not a decision that
 *  deserves a screen of its own — the manager has already decided they are
 *  out of time, and the dialog's job is to tell them what they are leaving
 *  with, not to talk them out of it.
 *
 *  **The button is never disabled.** Ending is the escape hatch, and an
 *  escape hatch that argues is not one. What the interview still owes is
 *  shown rather than enforced — the same shape the audit has, which reports
 *  and never blocks ([D3](../../../docs/DECISIONS.md#d3--the-agent-decides-code-only-audits-)).
 *
 *  The one thing worth saying plainly is when there is no shift vocabulary
 *  yet: with none declared there is no grid at all, not even a hand-built
 *  one, because inventing shift names is exactly what
 *  [D9](../../../docs/DECISIONS.md#d9--shift-vocabulary-is-per-workplace)
 *  forbids. That is a different sentence from "some things are missing", and
 *  the manager deserves to read it before they leave rather than discover it
 *  on an empty board.
 */
export function ConfirmEnd({
  draft,
  openPoints,
  busy,
  onConfirm,
  onCancel,
}: {
  draft: WorkplaceProfile | null;
  openPoints: string[];
  busy: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const shifts = draft?.shifts?.length ?? 0;
  const employees = draft?.employees?.length ?? 0;

  return (
    <div className="modal-backdrop" role="presentation" onClick={onCancel}>
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="end-interview-title"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="modal-header">
          <span className="modal-icon" aria-hidden="true">
            <DoorOpen size={18} />
          </span>
          <div>
            <h2 id="end-interview-title">לסיים את הראיון עכשיו?</h2>
            <p>מה שנאסף עד כה יישמר, ואפשר להשלים את השאר בכל שלב.</p>
          </div>
          <button
            type="button"
            className="icon-button"
            onClick={onCancel}
            aria-label="ביטול"
          >
            <X size={16} />
          </button>
        </header>

        <p className="modal-summary">
          נאספו {shifts} סוגי משמרות ו־{employees} עובדים.
        </p>

        {shifts === 0 ? (
          <p className="modal-note">
            <span className="modal-note-label">שימו לב</span>
            עדיין לא הוגדרו סוגי משמרות, ובלעדיהם אין לוח לבנות — גם לא ידנית.
            אפשר לסיים ולחזור לראיון מאיזור הניהול כשיהיה זמן.
          </p>
        ) : null}

        {openPoints.length ? (
          <div className="end-open-points">
            <span className="modal-note-label">מה שעוד לא סוכם</span>
            <ul>
              {openPoints.slice(0, 6).map((point, index) => (
                <li key={index}>{point}</li>
              ))}
            </ul>
            {openPoints.length > 6 ? (
              <p className="modal-hint">ועוד {openPoints.length - 6}.</p>
            ) : null}
          </div>
        ) : null}

        <p className="modal-hint">
          באיזור הניהול אפשר לשאול את הסוכן מה עוד חסר לו, ולחזור לראיון מהכפתור
          בסרגל העליון.
        </p>

        <div className="modal-actions">
          <button type="button" className="ghost-button" onClick={onCancel}>
            חזרה לראיון
          </button>
          <button
            type="button"
            className="primary-button"
            onClick={onConfirm}
            disabled={busy}
          >
            {busy ? "רגע…" : "סיום ומעבר לניהול"}
          </button>
        </div>
      </div>
    </div>
  );
}
