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
  onConfirm: (required: RequiredAssignment[]) => void;
  onCancel: () => void;
}) {
  const dates = useMemo(() => dateRange(weekStart, weekEnd), [weekStart, weekEnd]);
  const options = useMemo(() => shiftOptions(shifts), [shifts]);
  const nextId = useRef(2);
  const firstField = useRef<HTMLSelectElement>(null);
  const [rows, setRows] = useState<Row[]>(() => [newRow(
    1, employees, options, dates, weekStart,
  )]);

  useEffect(() => firstField.current?.focus(), []);
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
  const valid = rows.length > 0 && rows.every(
    (row) => row.employee && row.date && row.shift,
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
            <CalendarPlus size={17} /> בניית הסידור לשבוע
          </h2>
          <button type="button" className="icon-button" onClick={onCancel} aria-label="סגירה">
            <X size={17} />
          </button>
        </header>

        <p className="modal-summary">
          בחרו את השיבוצים שחייבים להופיע. הסוכן יבנה את שאר השבוע סביבם ולא
          יוכל להסיר או להחליף אותם.
        </p>

        <form onSubmit={(event) => {
          event.preventDefault();
          if (valid && !busy) {
            onConfirm(rows.map(({ employee, shift, date }) => ({ employee, shift, date })));
          }
        }}>
          <div className="generate-required-list">
            {rows.map((row, index) => {
              const availableShifts = shiftsForDate(options, row.date);
              return (
                <fieldset className="generate-required-row" key={row.id}>
                  <legend>שיבוץ חובה {index + 1}</legend>
                  <label>
                    <span>עובד/ת</span>
                    <select
                      ref={index === 0 ? firstField : undefined}
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
              newRow(nextId.current++, employees, options, dates, weekStart),
            ])}
          >
            <Plus size={15} /> הוספת שיבוץ חובה
          </button>

          <p className="modal-hint">
            טווח הבנייה: {hebrewWeekday(weekStart)} {formatDate(weekStart)} עד {hebrewWeekday(weekEnd)} {formatDate(weekEnd)}.
          </p>
          <div className="modal-actions">
            <button type="button" className="ghost-button" onClick={onCancel}>ביטול</button>
            <button type="submit" className="primary-button" disabled={!valid || busy}>
              {busy ? "בונה…" : "בניית הסידור עם שיבוצי החובה"}
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
