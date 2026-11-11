"use client";

import { AlertTriangle, UserMinus, X } from "lucide-react";
import { useEffect, useState } from "react";
import type { ReactNode } from "react";

import { DateInput, displayDate } from "@/components/DateInput";
import type { Departure } from "@/services/api";

/** Taking somebody off the roster, with what it costs counted first.
 *
 *  "Deleting" an employee is a departure, not an erasure. The name is the
 *  key their past shifts, their claimed identity and their colour on old
 *  boards hang on, so it stays in the profile with an end date and moves to
 *  the archive — the same thing the agent's `retire` plan does. What goes is
 *  every shift from that date on, and the dialog says how many before the
 *  click, plus which published weeks return to draft because of it.
 *
 *  The reason is offered, not required, for the reason `ConfirmRemoval`'s
 *  is: the person is leaving, there is nobody left on the roster for the
 *  sentence to be owed to, and the log already says a manager did it.
 *
 *  `covers` renders under the count for the date on screen — the changes
 *  tab puts who could take over the vacated shifts there. */
export function ConfirmDeparture({
  employee,
  today,
  busy,
  onPreview,
  onCancel,
  onConfirm,
  covers,
}: {
  employee: string;
  today: string;
  busy: boolean;
  onPreview: (input: { employee: string; effective_date?: string }) => Promise<Departure>;
  onCancel: () => void;
  onConfirm: (input: { effective_date: string; reason: string }) => void;
  covers?: (date: string) => ReactNode;
}) {
  const [date, setDate] = useState(today);
  const [reason, setReason] = useState("");
  // Keyed by the date it counted, so a count for a date no longer on screen
  // is never shown and never enables the button.
  const [counted, setCounted] = useState<{ date: string; preview?: Departure; error?: string } | null>(null);
  const preview = counted?.date === date ? counted.preview ?? null : null;
  const error = counted?.date === date ? counted.error ?? "" : "";

  useEffect(() => {
    let live = true;
    onPreview({ employee, effective_date: date })
      .then((result) => { if (live) setCounted({ date, preview: result }); })
      .catch((reason) => {
        if (live) setCounted({ date, error: reason instanceof Error ? reason.message : "שגיאה לא ידועה" });
      });
    return () => { live = false; };
  }, [employee, date, onPreview]);

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true">
      <div className="modal board-removal">
        <header className="modal-head">
          <h2>
            <UserMinus size={16} />
            הוצאת {employee} מהסגל
          </h2>
          <button type="button" className="icon-button" onClick={onCancel} aria-label="סגירה">
            <X size={16} />
          </button>
        </header>

        <label className="modal-field">
          <span>לא משובץ/ת החל מתאריך</span>
          <DateInput value={date} onChange={setDate} required />
        </label>

        <p className="board-removal-what" aria-live="polite">
          {error || (preview ? describe(preview) : "סופרים את המשמרות…")}
        </p>

        {preview?.published.length ? (
          <p className="board-removal-warning">
            <AlertTriangle size={15} aria-hidden="true" />
            <span>
              {preview.published.length === 1 ? "שבוע מפורסם חוזר" : `${preview.published.length} שבועות מפורסמים חוזרים`}
              {" "}לטיוטה ({preview.published.map((row) => displayDate(row.starts_on)).join(", ")}).
            </span>
          </p>
        ) : null}

        {covers ? covers(date) : null}

        <p className="board-removal-note">
          המשמרות שכבר עבר/ה, ההיסטוריה ויומן השינויים נשמרים. אפשר להחזיר
          לסגל מרשימת העובדים שסיימו — המשמרות שפונו לא חוזרות מעצמן.
        </p>

        <label className="modal-field">
          <span>סיבה (לא חובה)</span>
          <input
            value={reason}
            maxLength={1000}
            onChange={(event) => setReason(event.target.value)}
            placeholder="למשל: סיים/ה שירות"
          />
        </label>

        <footer className="modal-actions">
          <button type="button" className="ghost-button" onClick={onCancel}>
            ביטול
          </button>
          <button
            type="button"
            className="danger-button"
            onClick={() => onConfirm({ effective_date: date, reason: reason.trim() })}
            disabled={busy || !preview}
          >
            הוצאה מהסגל
          </button>
        </footer>
      </div>
    </div>
  );
}

function describe(preview: Departure): string {
  const from = displayDate(preview.effective_date);
  if (preview.shifts === 0) return `אין ל${preview.employee} משמרות מ-${from} והלאה.`;
  const what = preview.shifts === 1 ? "משמרת אחת" : `${preview.shifts} משמרות`;
  return `${what} של ${preview.employee} מ-${from} והלאה יפונו.`;
}
