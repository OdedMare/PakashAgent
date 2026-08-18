"use client";

import { ArrowLeftRight, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import type { Assignment } from "@/types";

import { formatDate, hebrewWeekday } from "./Calendar";

/** The dialog a drop opens. **This is what makes a drag legitimate.**
 *
 *  The gesture on the calendar changed nothing; this collects the manager's
 *  reason and only then writes
 *  ([D8](../../../docs/DECISIONS.md#d8--two-reasons-both-required)). Without
 *  it a dragged shift would land in the append-only log with no explanation,
 *  which is the one thing the log exists to prevent — "why did Yossi get
 *  moved" has to stay answerable.
 *
 *  The reason field is required and the confirm button stays disabled until
 *  it has content, so the requirement is visible rather than enforced by a
 *  server error after the fact. */
export function ConfirmMove({
  assignment,
  shiftName,
  slotDate,
  busy,
  onConfirm,
  onCancel,
}: {
  assignment: Assignment;
  shiftName: string;
  slotDate: string;
  busy: boolean;
  onConfirm: (reason: string) => void;
  onCancel: () => void;
}) {
  const [reason, setReason] = useState("");
  const field = useRef<HTMLInputElement>(null);

  // Focus lands on the thing the manager has to supply, so the dialog is
  // usable from the keyboard immediately after a mouse gesture.
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
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-move-title"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="modal-header">
          <h2 id="confirm-move-title">
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

        {/* The reason the agent gave for the original assignment. Shown
            because the manager is about to overrule it, and the judgment
            they are overruling should be in front of them when they do. */}
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
          {/* Said plainly rather than left implicit: the reason is not
              paperwork, it is what makes the change log answerable later. */}
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
