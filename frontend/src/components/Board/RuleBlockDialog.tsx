"use client";

import { ShieldAlert, X } from "lucide-react";
import { useEffect } from "react";

/** A hand placement that breaks one of the unit's hard rules.
 *
 *  The server refuses it as overridable (`RuleBlockedError`) and the board
 *  asks here instead of failing: on a hand-made schedule a hard rule is a
 *  loud warning, not a gate (D1/D3). "לשבץ בכל זאת" sends the same write
 *  with `override`, the change log records that the rule was overruled, and
 *  the audit keeps the warning on the board. An operational duty never
 *  reaches this dialog — it is occupied time and is refused outright. */
export function RuleBlockDialog({
  message,
  busy,
  onConfirm,
  onCancel,
}: {
  message: string;
  busy: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onCancel();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onCancel]);

  return (
    <div className="modal-backdrop" role="presentation" onClick={onCancel}>
      <div
        className="modal board-modal rule-block"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="rule-block-title"
        aria-describedby="rule-block-what"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="modal-header">
          <h2 id="rule-block-title">
            <ShieldAlert size={17} />
            חוק חוסם את השיבוץ
          </h2>
          <button type="button" className="icon-button" onClick={onCancel} aria-label="ביטול">
            <X size={17} />
          </button>
        </header>

        <p id="rule-block-what" className="rule-block-what">{message}</p>

        <p className="modal-hint">
          אפשר לשבץ בכל זאת. השיבוץ יירשם ביומן השינויים כחריגה מהחוק באישורך,
          והאזהרה תמשיך להופיע בלוח עד שהמצב יתוקן.
        </p>

        <div className="modal-actions">
          <button type="button" className="ghost-button" onClick={onCancel} autoFocus>
            ביטול
          </button>
          <button type="button" className="primary-button" disabled={busy} onClick={onConfirm}>
            {busy ? "משבץ…" : "לשבץ בכל זאת"}
          </button>
        </div>
      </div>
    </div>
  );
}
