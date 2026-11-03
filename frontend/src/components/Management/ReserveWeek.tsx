"use client";

import { useState } from "react";

import type { Constraint } from "@/types";

import { WEEKDAYS } from "./teamLabels";

/** A reservist's coming week in one row of seven days.
 *
 *  A reservist whose days change week to week tells the manager which days
 *  are bad, and the solver picks the rest (`reserve_days_per_week`,
 *  `reserve_min_days`). Each day cycles through three states, each stored
 *  as an ordinary whole-day availability row, so the board, the audit and
 *  the solver read it the way they read any other constraint:
 *
 *  - רגיל — nothing stored; the solver may place them.
 *  - עדיף שלא — a soft unavailability: priced like a wish.
 *  - לא יכול/ה — a hard unavailability: never placed. */
type DayState = "free" | "soft" | "hard";

const NEXT: Record<DayState, DayState> = { free: "soft", soft: "hard", hard: "free" };
const LABELS: Record<DayState, string> = { free: "רגיל", soft: "עדיף שלא", hard: "לא יכול/ה" };
const REASON = "מילואים: עדכון שבועי";

export function ReserveWeek({ name, today, constraints, onAdd, onRemove }: {
  name: string;
  today: string;
  constraints: Constraint[];
  onAdd: (input: { employee: string; constraint_date: string; available: boolean; is_hard: boolean; reason: string; source: string }) => void;
  onRemove: (rowId: string) => void;
}) {
  const [offset, setOffset] = useState(0);
  const sunday = addDays(sundayOf(today || isoToday()), offset * 7);
  const days = WEEKDAYS.map((_, index) => addDays(sunday, index));

  const rowsOn = (date: string) => constraints.filter((row) =>
    row.employee === name && row.constraint_date === date && row.constraint_type !== "duty"
    && !row.shift_name && !row.start_time && !row.end_time && !row.available);
  const stateOf = (date: string): DayState => {
    const rows = rowsOn(date);
    return rows.some((row) => row.is_hard) ? "hard" : rows.length ? "soft" : "free";
  };
  const cycle = (date: string) => {
    const next = NEXT[stateOf(date)];
    rowsOn(date).forEach((row) => onRemove(row.id));
    if (next !== "free") {
      onAdd({ employee: name, constraint_date: date, available: false, is_hard: next === "hard", reason: REASON, source: "employee_reported" });
    }
  };

  return (
    <div className="reserve-week">
      <div className="reserve-week-head">
        <strong>השבוע של {name}</strong>
        <div className="reserve-week-nav">
          <button type="button" className={`rotation-link${offset === 0 ? " is-active" : ""}`} onClick={() => setOffset(0)}>השבוע</button>
          <button type="button" className={`rotation-link${offset === 1 ? " is-active" : ""}`} onClick={() => setOffset(1)}>שבוע הבא</button>
        </div>
      </div>
      <div className="reserve-week-days">
        {days.map((date, index) => {
          const state = stateOf(date);
          return (
            <button key={date} type="button" className={`reserve-day is-${state}`} onClick={() => cycle(date)}
              aria-label={`${WEEKDAYS[index]} ${shortDay(date)}: ${LABELS[state]}. לחיצה משנה`}>
              <b>{WEEKDAYS[index].slice(0, 1)}׳</b>
              <span>{shortDay(date)}</span>
              <small>{LABELS[state]}</small>
            </button>
          );
        })}
      </div>
      <small className="reserve-week-hint">לחיצה על יום מחליפה: רגיל → עדיף שלא → לא יכול/ה. את שאר הימים בוחר הסידור לפי מספר הימים שהוגדר.</small>
    </div>
  );
}

function isoToday(): string {
  const now = new Date();
  return new Date(Date.UTC(now.getFullYear(), now.getMonth(), now.getDate())).toISOString().slice(0, 10);
}

function sundayOf(iso: string): string {
  const day = new Date(`${iso}T00:00:00Z`).getUTCDay();
  return addDays(iso, -day);
}

function addDays(iso: string, days: number): string {
  const date = new Date(`${iso}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

function shortDay(iso: string): string {
  return `${Number(iso.slice(8, 10))}.${Number(iso.slice(5, 7))}`;
}
