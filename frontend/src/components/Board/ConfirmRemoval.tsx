"use client";

import { AlertTriangle, Eraser, Trash2, X } from "lucide-react";
import { useState } from "react";

import { displayDate } from "@/components/DateInput";
import { hebrewWeekday } from "@/components/Management/Calendar";

/** What is about to be taken away.
 *
 *  Three shapes rather than one flag, because the three differ in what
 *  survives and a dialog that blurred them would be asking the manager to
 *  approve something they have to guess at:
 *
 *  - `day` — one date's assignments. The slots stay; the column is empty
 *    tomorrow morning and ready to be filled again.
 *  - `week` — the whole period's assignments, same deal, seven times over.
 *  - `period` — the period itself. The grid goes with it and the week
 *    returns to the state where it offers to be built. */
export type RemovalTarget =
  | { mode: "day"; date: string; count: number }
  | { mode: "week"; count: number }
  | { mode: "period"; count: number };

/** Confirming a removal, with what it costs stated plainly.
 *
 *  **This is not `ConfirmDrop`.** A drag takes a shift from one person and
 *  gives it to another, so it owes them a reason
 *  ([D8](../../../docs/DECISIONS.md#d8--two-reasons-both-required)) and the
 *  confirm button stays disabled until there is one. Clearing a day is the
 *  manager throwing away an outcome — usually one the agent just produced —
 *  and there is no one for the reason to be owed to. So the field is offered
 *  and never required: whatever they type is recorded against every removed
 *  row, and leaving it empty still says in the log that a person did this.
 *
 *  What *is* required is that the manager sees the size of it. A count, and
 *  for a period the fact that the grid goes too, because "delete" and
 *  "clear" are one click apart and only one of them can be undone by typing
 *  the names back in.
 */
export function ConfirmRemoval({
  target,
  busy,
  onCancel,
  onConfirm,
}: {
  target: RemovalTarget;
  busy: boolean;
  onCancel: () => void;
  onConfirm: (reason: string) => void;
}) {
  const [reason, setReason] = useState("");
  const destructive = target.mode === "period";

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true">
      <div className="modal board-removal">
        <header className="modal-head">
          <h2>
            {destructive ? <Trash2 size={16} /> : <Eraser size={16} />}
            {title(target)}
          </h2>
          <button
            type="button"
            className="icon-button"
            onClick={onCancel}
            aria-label="סגירה"
          >
            <X size={16} />
          </button>
        </header>

        <p className="board-removal-what">{describe(target)}</p>

        {destructive ? (
          <p className="board-removal-warning">
            <AlertTriangle size={15} aria-hidden="true" />
            <span>
              נמחקות גם שורות המשמרות של השבוע, לא רק השיבוצים. יומן השינויים
              נשמר — מה שנעשה בסידור עדיין מתועד גם אחרי שהסידור עצמו נמחק.
            </span>
          </p>
        ) : (
          <p className="board-removal-note">
            שורות המשמרות נשארות, כך שאפשר לשבץ מחדש מיד — ידנית או בבקשה
            מהסוכן.
          </p>
        )}

        <label className="modal-field">
          <span>סיבה (לא חובה)</span>
          <input
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder="למשל: בונים את היום מחדש אחרי שינוי בכוח האדם"
            autoFocus
          />
        </label>

        <footer className="modal-actions">
          <button type="button" className="ghost-button" onClick={onCancel}>
            ביטול
          </button>
          <button
            type="button"
            className={destructive ? "danger-button" : "primary-button"}
            onClick={() => onConfirm(reason.trim())}
            disabled={busy}
          >
            {destructive ? "מחיקת הסידור" : "מחיקת השיבוצים"}
          </button>
        </footer>
      </div>
    </div>
  );
}

function title(target: RemovalTarget): string {
  if (target.mode === "day") {
    return `מחיקת השיבוצים של ${hebrewWeekday(target.date)}`;
  }
  return target.mode === "week" ? "מחיקת השיבוצים של השבוע" : "מחיקת הסידור";
}

/** The size of what is going, in one sentence.
 *
 *  Counted rather than described: "3 שיבוצים" is checkable against the
 *  column the manager is looking at, and an empty day says so instead of
 *  offering to remove nothing. */
function describe(target: RemovalTarget): string {
  const what =
    target.count === 0
      ? "אין שיבוצים"
      : target.count === 1
        ? "שיבוץ אחד"
        : `${target.count} שיבוצים`;

  if (target.mode === "day") {
    return `${what} ב-${hebrewWeekday(target.date)} ${displayDate(target.date)}.`;
  }
  if (target.mode === "week") {
    return `${what} בשבוע הזה.`;
  }
  return `${what} בסידור, והשבוע חוזר למצב שבו הוא עוד לא נבנה.`;
}
