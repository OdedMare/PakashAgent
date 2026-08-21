"use client";

import { CalendarPlus, Plus, Trash2, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { formatDate, hebrewWeekday } from "@/components/Management/Calendar";
import type { RequiredAssignment } from "@/types";

type Row = RequiredAssignment & { id: number };

export function GenerateDialog({
  employees,
  shifts,
  weekStart,
  weekEnd,
  busy,
  onConfirm,
  onCancel,
}: {
  employees: string[];
  shifts: Record<string, unknown>[];
  weekStart: string;
  weekEnd: string;
  busy: boolean;
  onConfirm: (input: {
    starts_on: string;
    ends_on: string;
    instructions: string;
    required_assignments: RequiredAssignment[];
  }) => void;
  onCancel: () => void;
}) {
  const [startsOn, setStartsOn] = useState(weekStart);
  const [endsOn, setEndsOn] = useState(weekEnd);
  const [instructions, setInstructions] = useState("");
  const dates = useMemo(
    () => dateRange(startsOn, endsOn),
    [startsOn, endsOn],
  );
  const options = useMemo(() => shiftOptions(shifts), [shifts]);
  const nextId = useRef(1);
  const [rows, setRows] = useState<Row[]>([]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onCancel();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onCancel]);

  const update = (id: number, patch: Partial<Row>) => {
    setRows((current) => current.map((row) => {
      if (row.id !== id) return row;
      const next = { ...row, ...patch };
      if (patch.date) {
        const available = shiftsForDate(options, patch.date);
        if (!available.some((shift) => shift.name === next.shift)) {
          next.shift = available[0]?.name ?? "";
        }
      }
      return next;
    }));
  };
  const validRange = dates.length > 0 && startsOn <= endsOn;
  const valid = validRange && rows.every(
    (row) => row.employee && dates.includes(row.date) && row.shift,
  );

  return (
    <div className="modal-backdrop" role="presentation" onClick={onCancel}>
      <div
        className="modal board-modal generate-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="generate-dialog-title"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="modal-header">
          <h2 id="generate-dialog-title">
            <CalendarPlus size={17} /> בניית סידור לתאריך או לטווח
          </h2>
          <button type="button" className="icon-button" onClick={onCancel} aria-label="סגירה">
            <X size={17} />
          </button>
        </header>

        <p className="modal-summary">
          בחרו טווח, הוסיפו כללים לבקשה, ואם צריך גם שיבוצים שחייבים להופיע.
          הסוכן יבנה כל יום בנפרד ויתחשב בכל מה שכבר נקבע.
        </p>

        <form onSubmit={(event) => {
          event.preventDefault();
          if (valid && !busy) {
            onConfirm({
              starts_on: startsOn,
              ends_on: endsOn,
              instructions: instructions.trim(),
              required_assignments: rows.map(({ employee, shift, date }) => ({ employee, shift, date })),
            });
          }
        }}>
          <fieldset className="generate-required-row">
            <legend>טווח התכנון</legend>
            <label>
              <span>מתאריך</span>
              <input
                type="date"
                value={startsOn}
                onChange={(event) => setStartsOn(event.target.value)}
                required
              />
            </label>
            <label>
              <span>עד תאריך</span>
              <input
                type="date"
                min={startsOn}
                value={endsOn}
                onChange={(event) => setEndsOn(event.target.value)}
                required
              />
            </label>
            <label>
              <span>כללים נוספים לבנייה הזאת</span>
              <textarea
                value={instructions}
                maxLength={2000}
                placeholder="לדוגמה: השבוע להעדיף את דנה בבקרים"
                onChange={(event) => setInstructions(event.target.value)}
              />
            </label>
          </fieldset>
          <div className="generate-required-list">
            {rows.map((row, index) => {
              const availableShifts = shiftsForDate(options, row.date);
              return (
                <fieldset className="generate-required-row" key={row.id}>
                  <legend>שיבוץ חובה {index + 1}</legend>
                  <label>
                    <span>עובד/ת</span>
                    <select
                      value={row.employee}
                      onChange={(event) => update(row.id, { employee: event.target.value })}
                      required
                    >
                      {employees.map((employee) => <option key={employee}>{employee}</option>)}
                    </select>
                  </label>
                  <label>
                    <span>יום</span>
                    <select
                      value={row.date}
                      onChange={(event) => update(row.id, { date: event.target.value })}
                      required
                    >
                      {dates.map((date) => (
                        <option key={date} value={date}>
                          {hebrewWeekday(date)} · {formatDate(date)}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    <span>משמרת ושעה</span>
                    <select
                      value={row.shift}
                      onChange={(event) => update(row.id, { shift: event.target.value })}
                      required
                    >
                      {availableShifts.map((shift) => (
                        <option key={shift.name} value={shift.name}>
                          {shift.name}{shift.hours ? ` · ${shift.hours}` : ""}
                        </option>
                      ))}
                    </select>
                  </label>
                  {rows.length > 1 ? (
                    <button
                      type="button"
                      className="icon-button generate-remove"
                      onClick={() => setRows((current) => current.filter((item) => item.id !== row.id))}
                      aria-label={`מחיקת שיבוץ חובה ${index + 1}`}
                    >
                      <Trash2 size={16} />
                    </button>
                  ) : null}
                </fieldset>
              );
            })}
          </div>

          <button
            type="button"
            className="ghost-button generate-add"
            onClick={() => setRows((current) => [
              ...current,
              newRow(nextId.current++, employees, options, dates, startsOn),
            ])}
          >
            <Plus size={15} /> הוספת שיבוץ חובה
          </button>

          <p className="modal-hint">
            טווח הבנייה: {hebrewWeekday(startsOn)} {formatDate(startsOn)} עד {hebrewWeekday(endsOn)} {formatDate(endsOn)}. כללי מקום העבודה והאילוצים הקיימים חלים על כל יום.
          </p>
          <div className="modal-actions">
            <button type="button" className="ghost-button" onClick={onCancel}>ביטול</button>
            <button type="submit" className="primary-button" disabled={!valid || busy}>
              {busy ? "בונה…" : dates.length === 1 ? "בניית הסידור ליום" : `בניית הסידור ל-${dates.length} ימים`}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

type ShiftOption = { name: string; hours: string; days: string[] };

function shiftOptions(rows: Record<string, unknown>[]): ShiftOption[] {
  return rows.flatMap((row) => {
    const name = typeof row.name === "string" ? row.name.trim() : "";
    if (!name) return [];
    const start = typeof row.start_time === "string" ? row.start_time : "";
    const end = typeof row.end_time === "string" ? row.end_time : "";
    const days = Array.isArray(row.days)
      ? row.days.filter((day): day is string => typeof day === "string")
      : [];
    return [{ name, hours: start && end ? `${start}–${end}` : "", days }];
  });
}

function shiftsForDate(shifts: ShiftOption[], date: string): ShiftOption[] {
  const weekday = hebrewWeekday(date).replace(/^יום /, "");
  return shifts.filter((shift) =>
    !shift.days.length || shift.days.some((day) => day.replace(/^יום /, "") === weekday),
  );
}

function dateRange(first: string, last: string): string[] {
  const dates: string[] = [];
  const cursor = new Date(`${first}T00:00:00`);
  const end = new Date(`${last}T00:00:00`);
  while (cursor <= end) {
    dates.push([
      cursor.getFullYear(),
      String(cursor.getMonth() + 1).padStart(2, "0"),
      String(cursor.getDate()).padStart(2, "0"),
    ].join("-"));
    cursor.setDate(cursor.getDate() + 1);
  }
  return dates;
}

function newRow(
  id: number,
  employees: string[],
  shifts: ShiftOption[],
  dates: string[],
  fallbackDate: string,
): Row {
  const date = dates.find((day) => shiftsForDate(shifts, day).length > 0)
    ?? fallbackDate;
  return {
    id,
    employee: employees[0] ?? "",
    date,
    shift: shiftsForDate(shifts, date)[0]?.name ?? "",
  };
}
