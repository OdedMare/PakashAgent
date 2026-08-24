"use client";

import { CalendarClock, Sparkles, X } from "lucide-react";
import { useEffect, useState } from "react";

import { formatDate, hebrewWeekday } from "@/components/Management/Calendar";

export function GenerateDayDialog({
  date,
  busy,
  onConfirm,
  onCancel,
}: {
  date: string;
  busy: boolean;
  onConfirm: (instructions: string) => void;
  onCancel: () => void;
}) {
  const [instructions, setInstructions] = useState("");

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
        className="modal board-modal generate-day-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="generate-day-title"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="modal-header">
          <h2 id="generate-day-title">
            <CalendarClock size={17} /> שיבוץ יום ספציפי
          </h2>
          <button type="button" className="icon-button" onClick={onCancel} aria-label="סגירה">
            <X size={17} />
          </button>
        </header>

        <div className="generate-day-date">
          <span>{hebrewWeekday(date)}</span>
          <strong>{formatDate(date)}</strong>
        </div>

        <label className="generate-instructions">
          <span>מה חשוב לסוכן ביום הזה? <small>לא חובה</small></span>
          <textarea
            value={instructions}
            maxLength={2000}
            autoFocus
            placeholder="לדוגמה: זה יום הסגירה של קבוצה א; לשמור על הסבב ולתת עדיפות למי שלא סגר בשבת הקודמת"
            onChange={(event) => setInstructions(event.target.value)}
          />
        </label>

        <p className="modal-hint">
          הסוכן ישבץ מחדש רק את היום הזה. שיבוצים ידניים נשארים קבועים,
          ושאר הימים לא משתנים.
        </p>

        <div className="modal-actions">
          <button type="button" className="ghost-button" onClick={onCancel}>ביטול</button>
          <button
            type="button"
            className="primary-button"
            disabled={busy}
            onClick={() => onConfirm(instructions.trim())}
          >
            <Sparkles size={15} />
            {busy ? "מתחיל…" : "שיבוץ היום"}
          </button>
        </div>
      </div>
    </div>
  );
}
