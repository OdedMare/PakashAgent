"use client";

import { ArrowLeftRight, CheckCircle2, TriangleAlert, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { formatDate, hebrewWeekday } from "@/components/Management/Calendar";
import type { Assignment, PlacementCheck } from "@/types";

/** The dialog a drop opens — the same contract `ConfirmMove` has, plus what
 *  the move would cost.
 *
 *  **The drag still wrote nothing** ([D12](../../../docs/DECISIONS.md#d12--dragging-a-shift-is-a-proposal-not-an-edit)),
 *  and the manager's reason is still required before anything lands
 *  ([D8](../../../docs/DECISIONS.md#d8--two-reasons-both-required)). What is
 *  added is that the consequences arrive *here*, before the click, instead
 *  of as a warning banner after the schedule already moved.
 *
 *  That check is `bl/placement.py` — pure arithmetic, **no model call** — so
 *  this dialog is fully functional with the agent unavailable. The manager
 *  never has to phrase anything to an AI to find out that דנה has a
 *  constraint that day.
 *
 *  **It explains; it does not refuse.** The confirm button is live whatever
 *  the check found, because the audit advises and never gates
 *  ([D3](../../../docs/DECISIONS.md#d3--the-agent-decides-code-only-audits-)) —
 *  a manager who knows about the constraint and wants the move anyway is
 *  making a decision, not a mistake. Only the reason gates, and it gates for
 *  a different purpose entirely.
 */
export function ConfirmDrop({
  assignment,
  shiftName,
  slotDate,
  check,
  checking,
  busy,
  onConfirm,
  onCancel,
  onPickAlternativeSlot,
}: {
  assignment: Assignment;
  shiftName: string;
  slotDate: string;
  /** What the move would cost. Null while the check is in flight, or when
   *  it failed — a check that could not be made must not stop the manager. */
  check: PlacementCheck | null;
  checking: boolean;
  busy: boolean;
  onConfirm: (reason: string) => void;
  onCancel: () => void;
  /** Move to a different slot instead of the one dropped on. */
  onPickAlternativeSlot?: (input: {
    shift_name: string;
    slot_date: string;
  }) => void;
}) {
  const [reason, setReason] = useState("");
  const field = useRef<HTMLInputElement>(null);

  useEffect(() => {
    field.current?.focus();
  }, []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onCancel();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onCancel]);

  const ready = reason.trim().length > 0 && !busy;

  return (
    <div className="modal-backdrop" role="presentation" onClick={onCancel}>
      <div
        className="modal board-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-drop-title"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="modal-header">
          <h2 id="confirm-drop-title">
            <ArrowLeftRight size={17} />
            אישור העברת משמרת
          </h2>
          <button
            type="button"
            className="icon-button"
            onClick={onCancel}
            aria-label="ביטול"
          >
            <X size={17} />
          </button>
        </header>

        <p className="modal-summary">
          <strong>{assignment.employee}</strong> יעבור מ־
          <strong>
            {assignment.shift} · {hebrewWeekday(assignment.date)}{" "}
            {formatDate(assignment.date)}
          </strong>{" "}
          אל{" "}
          <strong>
            {shiftName} · {hebrewWeekday(slotDate)} {formatDate(slotDate)}
          </strong>
          .
        </p>

        <PlacementVerdict
          check={check}
          checking={checking}
          onPickSlot={onPickAlternativeSlot}
        />

        {/* The reason the agent gave for the original assignment. Shown
            because the manager is about to overrule it. */}
        {assignment.reason ? (
          <p className="modal-note">
            <span className="modal-note-label">הנימוק לשיבוץ המקורי</span>
            {assignment.reason}
          </p>
        ) : null}

        <form
          onSubmit={(event) => {
            event.preventDefault();
            if (ready) onConfirm(reason.trim());
          }}
        >
          <label className="modal-field">
            <span>
              למה המשמרת עוברת? <span aria-hidden="true">*</span>
            </span>
            <input
              ref={field}
              type="text"
              value={reason}
              maxLength={200}
              onChange={(event) => setReason(event.target.value)}
              placeholder="מחלה, בקשת העובד, כיסוי חוסר…"
              required
            />
          </label>
          <p className="modal-hint">
            הסיבה נשמרת ביומן השינויים לצד השם — היא מה שמאפשר לענות אחר כך על
            שאלות כמו כמה ימי מחלה נלקחו.
          </p>

          <div className="modal-actions">
            <button type="button" className="ghost-button" onClick={onCancel}>
              ביטול
            </button>
            <button type="submit" className="primary-button" disabled={!ready}>
              {busy ? "מעביר…" : "אישור ההעברה"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

/** What the deterministic check found, and what else could be done.
 *
 *  Exported because the shift editor shows the same verdict for the same
 *  reason — one voice for "here is what this placement costs", whether the
 *  manager got here by dragging or by picking a name from a list. */
export function PlacementVerdict({
  check,
  checking,
  onPickSlot,
  onPickEmployee,
}: {
  check: PlacementCheck | null;
  checking: boolean;
  onPickSlot?: (input: { shift_name: string; slot_date: string }) => void;
  onPickEmployee?: (employee: string) => void;
}) {
  if (checking) {
    return (
      <p className="board-verdict is-checking" aria-live="polite">
        בודק את השיבוץ…
      </p>
    );
  }
  // A check that failed says nothing rather than claiming everything is
  // fine. The audit under the board reports the same facts a moment after
  // the write, so the information is not lost — only its timing.
  if (!check) return null;

  if (check.ok) {
    return (
      <p className="board-verdict is-clear" aria-live="polite">
        <CheckCircle2 size={15} />
        לא נמצאה התנגשות בשיבוץ הזה.
      </p>
    );
  }

  return (
    <div className="board-verdict is-warning" aria-live="polite">
      <p className="board-verdict-head">
        <TriangleAlert size={15} />
        מה שיקרה אם השיבוץ הזה יישמר
      </p>
      <ul className="board-verdict-reasons">
        {check.reasons.map((reason, index) => (
          <li key={index}>{reason}</li>
        ))}
      </ul>

      {check.alternatives.employees.length && onPickEmployee ? (
        <div className="board-alternatives">
          <span className="board-alternatives-label">
            עובדים פנויים ומתאימים למשמרת
          </span>
          <div className="board-alternatives-row">
            {check.alternatives.employees.map((option) => (
              <button
                key={option.employee}
                type="button"
                className="board-alternative"
                onClick={() => onPickEmployee(option.employee)}
                title={option.why}
              >
                {option.employee}
                <span className="board-alternative-hours">
                  {option.hours} ש׳
                </span>
              </button>
            ))}
          </div>
        </div>
      ) : null}

      {check.alternatives.borrow?.length && onPickEmployee ? (
        <div className="board-alternatives is-borrow">
          {/* Its own heading, deliberately worded as a request rather than
              as availability. These people are on their exit: choosing one
              is asking them to come in on a weekend that is not theirs,
              and the dialog must not let that read as "free" (D25). */}
          <span className="board-alternatives-label">
            אין אף אחד מהסגירה — אפשר להציע למי שאינו בסגירה, באישורך
          </span>
          <div className="board-alternatives-row">
            {check.alternatives.borrow.map((option) => (
              <button
                key={option.employee}
                type="button"
                className="board-alternative is-borrow"
                onClick={() => onPickEmployee(option.employee)}
                title={option.why}
              >
                {option.employee}
                <span className="board-alternative-hours">
                  {option.rotation}
                </span>
              </button>
            ))}
          </div>
        </div>
      ) : null}

      {check.alternatives.slots.length && onPickSlot ? (
        <div className="board-alternatives">
          <span className="board-alternatives-label">
            משמרות סמוכות שפנויות עבורו/ה
          </span>
          <div className="board-alternatives-row">
            {check.alternatives.slots.map((option) => (
              <button
                key={`${option.shift_name}|${option.slot_date}`}
                type="button"
                className="board-alternative"
                onClick={() =>
                  onPickSlot({
                    shift_name: option.shift_name,
                    slot_date: option.slot_date,
                  })
                }
                title={option.why}
              >
                {option.shift_name}
                <span className="board-alternative-hours">
                  {hebrewWeekday(option.slot_date)} {formatDate(option.slot_date)}
                </span>
              </button>
            ))}
          </div>
        </div>
      ) : null}

      {/* Said outright. A dialog that lists problems and then offers a live
          confirm button is otherwise ambiguous about which of the two it
          means — and under D3 it means both. */}
      <p className="board-verdict-foot">
        אפשר להמשיך בכל מקרה — ההתראות מיידעות ולא חוסמות.
      </p>
    </div>
  );
}
