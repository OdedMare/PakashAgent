"use client";

import { DateInput } from "@/components/DateInput";
import { TimeInput } from "@/components/TimeInput";

import { WEEKDAYS } from "./teamLabels";

/** The questions one soldier's own exit pattern asks, under the pattern.
 *
 *  `daily` — which days they come and the hours they are on base.
 *  `personal` — one weekend in how many, and the first one they close.
 *  Every other pattern is answered by its group or its cycle, so nothing
 *  is rendered for it. */
export type ExitField = "daily_days" | "daily_start" | "daily_end" | "closure_every" | "closure_from";

export function ExitPatternFields({ pattern, person, onChange }: {
  pattern: string;
  person: Record<string, unknown>;
  onChange: (field: ExitField, value: string | number | string[] | null) => void;
}) {
  if (pattern === "daily") {
    const days = Array.isArray(person.daily_days) ? person.daily_days.filter((day): day is string => typeof day === "string") : [];
    return (
      <fieldset className="soldier-reserve exit-pattern-fields">
        <legend>הגעה יומית</legend>
        <div className="exit-day-picks" role="group" aria-label="ימי הגעה">
          {WEEKDAYS.map((day) => (
            <label key={day} className={`exit-day${days.includes(day) ? " is-selected" : ""}`}>
              <input type="checkbox" checked={days.includes(day)} onChange={(event) => onChange("daily_days", event.target.checked ? WEEKDAYS.filter((item) => item === day || days.includes(item)) : days.filter((item) => item !== day))} />
              <span>{day.slice(0, 1)}׳</span>
            </label>
          ))}
        </div>
        <div className="soldier-grid">
          <label className="soldier-field"><span>מגיע/ה בשעה</span><TimeInput value={str(person.daily_start)} onChange={(time) => onChange("daily_start", time)} /></label>
          <label className="soldier-field"><span>הולך/ת הביתה בשעה</span><TimeInput value={str(person.daily_end)} onChange={(time) => onChange("daily_end", time)} /></label>
        </div>
        <small>{days.length ? "" : "לא נבחרו ימים — מגיע/ה בכל ימי הפעילות. "}משמרת שחורגת מהשעות לא תשובץ לו/ה.</small>
      </fieldset>
    );
  }
  if (pattern === "personal") {
    const every = typeof person.closure_every === "number" ? person.closure_every : null;
    return (
      <fieldset className="soldier-reserve exit-pattern-fields">
        <legend>סגירה אישית</legend>
        <div className="soldier-grid">
          <label className="soldier-field">
            <span>סוגר/ת שבת אחת מכל</span>
            <select value={every ?? ""} onChange={(event) => onChange("closure_every", event.target.value ? Number(event.target.value) : null)}>
              <option value="">בחירה</option>
              {[2, 3, 4, 5, 6, 7, 8].map((count) => <option key={count} value={count}>{count} שבתות (1ל{count})</option>)}
            </select>
          </label>
          <label className="soldier-field"><span>סופ״ש הסגירה הראשון (תאריך כלשהו בו)</span><DateInput value={str(person.closure_from)} onChange={(iso) => onChange("closure_from", iso)} /></label>
        </div>
        <small>בסופ״ש שלו/ה בבסיס מחמישי עד החילוף בראשון; בשאר הסופ״שים בבית. באמצע השבוע — כרגיל.</small>
      </fieldset>
    );
  }
  return null;
}

function str(value: unknown): string {
  return typeof value === "string" ? value : "";
}
