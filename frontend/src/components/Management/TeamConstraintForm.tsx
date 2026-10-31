"use client";

import { useState } from "react";

import { DateInput } from "@/components/DateInput";
import { TimeInput } from "@/components/TimeInput";

import { WEEKDAYS, text } from "./teamLabels";

/** Recording one constraint.
 *
 *  `source` is a real question rather than a hidden default: whether the
 *  manager decided this or an employee reported it is exactly the
 *  distinction the schema keeps, and asking costs one select. */
export function ConstraintForm({
  names,
  shiftNames,
  onCancel,
  onSubmit,
}: {
  names: string[];
  shiftNames: string[];
  onCancel: () => void;
  onSubmit: (input: {
    employee: string;
    constraint_date: string;
    shift_name?: string;
    available?: boolean;
    start_time?: string;
    end_time?: string;
    is_hard?: boolean;
    reason?: string;
    source?: string;
    constraint_type?: "availability" | "duty";
    duration: "temporary" | "permanent";
    weekdays: string[];
  }) => void;
}) {
  const [employee, setEmployee] = useState(names[0] ?? "");
  const [date, setDate] = useState("");
  const [shift, setShift] = useState("");
  const [kind, setKind] = useState<"unavailable" | "window" | "duty">("unavailable");
  const [startTime, setStartTime] = useState("");
  const [endTime, setEndTime] = useState("");
  const [isHard, setIsHard] = useState(true);
  const [reason, setReason] = useState("");
  const [source, setSource] = useState("manager");
  const [duration, setDuration] = useState<"temporary" | "permanent">("temporary");
  const [weekdays, setWeekdays] = useState<string[]>([]);

  const ready =
    employee.trim() !== "" &&
    (duration === "permanent" ? weekdays.length > 0 : date !== "") &&
    (kind === "unavailable" || kind === "window" && (startTime !== "" || endTime !== "")
      || kind === "duty" && startTime !== "" && endTime !== "");

  return (
    <form
      className="constraint-form"
      onSubmit={(event) => {
        event.preventDefault();
        if (!ready) return;
        onSubmit({
          employee: employee.trim(),
          constraint_date: date,
          shift_name: shift,
          available: kind === "window",
          start_time: kind === "window" || kind === "duty" ? startTime : "",
          end_time: kind === "window" || kind === "duty" ? endTime : "",
          is_hard: kind === "duty" ? true : isHard,
          reason: reason.trim(),
          source,
          constraint_type: kind === "duty" ? "duty" : "availability",
          duration,
          weekdays,
        });
      }}
    >
      <label>
        <span>עובד</span>
        {names.length ? (
          <select
            value={employee}
            onChange={(event) => setEmployee(event.target.value)}
          >
            {names.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        ) : (
          <input
            type="text"
            value={employee}
            onChange={(event) => setEmployee(event.target.value)}
          />
        )}
      </label>

      <label>
        <span>משך האילוץ</span>
        <select value={duration} onChange={(event) => setDuration(event.target.value as "temporary" | "permanent")}>
          <option value="temporary">זמני — לתאריך מסוים</option>
          <option value="permanent">קבוע — חוזר בכל שבוע</option>
        </select>
      </label>

      {duration === "temporary" ? <label>
        <span>תאריך</span>
        <DateInput
          value={date}
          onChange={setDate}
          required
        />
      </label> : <fieldset className="profile-checkboxes"><legend>ימים קבועים</legend>{WEEKDAYS.map((day) => <label key={day}><input type="checkbox" checked={weekdays.includes(day)} onChange={(event) => setWeekdays(event.target.checked ? [...weekdays, day] : weekdays.filter((value) => value !== day))} /><span>{day}</span></label>)}</fieldset>}

      {kind !== "duty" ? <label>
        <span>משמרת</span>
        <select
          value={shift}
          onChange={(event) => setShift(event.target.value)}
        >
          {/* The empty option is the whole-day constraint, which is the
              profile's own convention and how the audit reads it. */}
          <option value="">כל היום</option>
          {shiftNames.map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </select>
      </label> : null}

      <label>
        <span>סוג רישום</span>
        <select
          value={kind}
          onChange={(event) => {
            const next = event.target.value as "unavailable" | "window" | "duty";
            setKind(next);
            if (next === "duty") setShift("");
          }}
        >
          <option value="unavailable">לא זמין/ה</option>
          <option value="window">זמין/ה רק בחלון שעות</option>
          <option value="duty">תורנות חוסמת</option>
        </select>
      </label>

      {kind === "window" || kind === "duty" ? (
        <div className="constraint-time-grid">
          <label>
            <span>{kind === "duty" ? "תחילת התורנות" : "יכול/ה להתחיל מ־"}</span>
            <TimeInput
              value={startTime}
              onChange={setStartTime}
            />
          </label>
          <label>
            <span>{kind === "duty" ? "סיום התורנות" : "חייב/ת לסיים עד"}</span>
            <TimeInput
              value={endTime}
              onChange={setEndTime}
            />
          </label>
          <small>{kind === "duty" ? "סיום מוקדם משעת ההתחלה נחשב לתורנות שחוצה חצות." : "אפשר למלא רק אחד מהגבולות. למשל 16:00 בלבד."}</small>
        </div>
      ) : null}

      {kind !== "duty" ? <label>
        <span>עוצמת האילוץ</span>
        <select
          value={isHard ? "hard" : "soft"}
          onChange={(event) => setIsHard(event.target.value === "hard")}
        >
          <option value="hard">קשיח — אין לשבץ בניגוד אליו</option>
          <option value="soft">העדפה — אפשר לחרוג כשצריך</option>
        </select>
      </label> : null}

      <label>
        <span>סיבה</span>
        <input
          type="text"
          value={reason}
          maxLength={200}
          onChange={(event) => setReason(event.target.value)}
          placeholder={kind === "duty" ? "מטבח, שמירה, תורנות חמ״ל…" : "מחלה, לימודים, מילואים…"}
        />
      </label>

      <label>
        <span>מקור</span>
        <select
          value={source}
          onChange={(event) => setSource(event.target.value)}
        >
          <option value="manager">המנהל קבע</option>
          <option value="employee_reported">העובד מסר</option>
        </select>
      </label>

      <div className="constraint-form-actions">
        <button type="button" className="ghost-button" onClick={onCancel}>
          ביטול
        </button>
        <button type="submit" className="primary-button" disabled={!ready}>
          שמירה
        </button>
      </div>
    </form>
  );
}
