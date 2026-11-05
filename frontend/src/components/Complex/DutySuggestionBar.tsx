"use client";

import { AlertTriangle, Check, X } from "lucide-react";

import { displayDate } from "@/components/DateInput";
import type { DutyApproval, DutySuggestion } from "@/types";

import { conflictLine } from "./dutyText";

/** The proposal of "מלא בהוגנות", above the grid that draws its picks, and
 *  then what the approval did. Nothing is saved until "אישור"; a pick the
 *  commander removes from the grid is simply not sent (D20). */
export function DutySuggestionBar({
  suggestion,
  approval,
  busy,
  onApprove,
  onDiscard,
}: {
  suggestion: DutySuggestion | null;
  approval: DutyApproval | null;
  busy: boolean;
  onApprove: () => void;
  onDiscard: () => void;
}) {
  if (approval) {
    return (
      <section className="duty-suggestion" role="status" aria-label="תוצאת האישור">
        <header>
          <strong>{approval.saved.length} תורנויות נשמרו</strong>
          <button type="button" className="icon-button subtle" onClick={onDiscard} aria-label="סגירה">
            <X size={15} />
          </button>
        </header>
        {approval.failed.length ? (
          <div className="duty-conflicts">
            <AlertTriangle size={15} aria-hidden="true" />
            <div>
              <strong>{approval.failed.length} לא נשמרו:</strong>
              <ul>
                {approval.failed.map((row) => (
                  <li key={`${row.duty_date}-${row.team_id}-${row.employee}`}>
                    {displayDate(row.duty_date)} · {row.duty_type} · {row.employee}: {row.error}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        ) : null}
        {approval.conflicts.length ? (
          <div className="duty-conflicts">
            <AlertTriangle size={15} aria-hidden="true" />
            <div>
              <strong>משמרות שהתורנויות חסמו:</strong>
              <ul>
                {approval.conflicts.map((row) => (
                  <li key={`${row.team_id}-${row.employee}-${row.date}-${row.shift_name}`}>{conflictLine(row)}</li>
                ))}
              </ul>
            </div>
          </div>
        ) : null}
      </section>
    );
  }
  if (!suggestion) return null;

  return (
    <section className="duty-suggestion" aria-label="הצעת חלוקה הוגנת">
      <header>
        <strong>
          {suggestion.proposals.length
            ? `הצעה: ${suggestion.proposals.length} שיבוצים`
            : "אין מקומות פנויים להציע בטווח הזה"}
        </strong>
        <span className="cmd-hint">
          לפי תורנויות מ־{displayDate(suggestion.window_start)}: אף חייל לא מקבל תורנות בפחות משישה ימים
          מתורנות אחרת שלו (לפני או אחרי) כל עוד יש מישהו פנוי אחר, ואז — הכי מעט תורנויות, סופ״ש, המרווח
          הגדול ביותר, מי שאין לו משמרת שהתורנות תחסום, והעומס הכולל. מי שבבית, עם אילוץ או בתורנות אחרת —
          לא מוצע. כל הצעה מסבירה את עצמה במעבר עכבר, ואפשר להסיר הצעה מהטבלה לפני האישור.
        </span>
      </header>
      {suggestion.unfilled.length ? (
        <p className="duty-unfilled">
          <AlertTriangle size={14} aria-hidden="true" /> לא נמצא חייל זמין ל־{suggestion.unfilled.length} מקומות:{" "}
          {suggestion.unfilled.slice(0, 6).map((row) => `${row.duty_type} ${displayDate(row.duty_date)}`).join(", ")}
          {suggestion.unfilled.length > 6 ? "…" : ""}
        </p>
      ) : null}
      <div className="duty-suggestion-actions">
        <button type="button" className="primary-button" disabled={busy || !suggestion.proposals.length}
          onClick={onApprove}>
          <Check size={15} /> אישור {suggestion.proposals.length} השיבוצים
        </button>
        <button type="button" className="ghost-button" disabled={busy} onClick={onDiscard}>ביטול</button>
      </div>
    </section>
  );
}
