"use client";

import { AlertTriangle, Moon, Users } from "lucide-react";
import { useState } from "react";

import type { Assignment, Constraint, Schedule, Slot } from "@/types";

/** The living schedule as a week grid, right-to-left.
 *
 *  Dragging an assignment does **not** edit anything. The drop opens a
 *  confirmation that collects the manager's reason, and only that dialog
 *  writes ([D8](../../../docs/DECISIONS.md#d8--two-reasons-both-required)).
 *  This keeps the direct-manipulation feel of a calendar without letting a
 *  gesture put a row in the schedule that nobody can account for — the drag
 *  is a way of *proposing* a move, which is the same thing typing "move Dana
 *  to Tuesday" does.
 *
 *  Warnings are painted onto the cells they belong to and never prevent a
 *  drop ([D3](../../../docs/DECISIONS.md#d3--the-agent-decides-code-only-audits-)).
 *  A cell can be short-staffed, double-booked, and still perfectly draggable:
 *  the manager is the one who decides, and the grid only has to tell them. */
export function Calendar({
  schedule,
  constraints,
  readOnly = false,
  onDrop,
}: {
  schedule: Schedule;
  constraints: Constraint[];
  readOnly?: boolean;
  onDrop?: (move: {
    assignment: Assignment;
    shift_name: string;
    slot_date: string;
  }) => void;
}) {
  const [dragging, setDragging] = useState<Assignment | null>(null);
  const [over, setOver] = useState<string | null>(null);

  const dates = uniqueSorted(schedule.slots.map((slot) => slot.slot_date));
  // Shift rows keep the order the vocabulary gave them, by first appearance,
  // rather than being sorted alphabetically — a workplace's shifts have a
  // natural order (morning, then evening, then on-call) that alphabetising
  // would scramble.
  const shifts = uniqueByAppearance(
    schedule.slots.map((slot) => slot.shift_name),
  );

  const assignmentsFor = (shift: string, date: string) =>
    schedule.assignments.filter(
      (row) => row.shift === shift && row.date === date,
    );

  const slotFor = (shift: string, date: string): Slot | undefined =>
    schedule.slots.find(
      (slot) => slot.shift_name === shift && slot.slot_date === date,
    );

  return (
    <div className="calendar-scroll">
      <table className="calendar" dir="rtl">
        <caption className="visually-hidden">
          סידור העבודה מ-{formatDate(schedule.starts_on)} עד{" "}
          {formatDate(schedule.ends_on)}
        </caption>
        <thead>
          <tr>
            <th scope="col" className="calendar-corner">
              משמרת
            </th>
            {dates.map((date) => (
              <th key={date} scope="col">
                <span className="calendar-weekday">{hebrewWeekday(date)}</span>
                <span className="calendar-date">{formatDate(date)}</span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {shifts.map((shift) => (
            <tr key={shift}>
              <th scope="row" className="calendar-shift">
                {shift}
                <ShiftTimes slot={slotFor(shift, dates[0])} shift={shift}
                  slots={schedule.slots} />
              </th>
              {dates.map((date) => {
                const slot = slotFor(shift, date);
                const key = `${shift}|${date}`;
                const rows = assignmentsFor(shift, date);
                const cellWarnings = schedule.warnings.filter(
                  (warning) =>
                    warning.date === date &&
                    (warning.shift === shift || warning.shift === ""),
                );
                // A slot that does not exist on this date is not a gap in the
                // schedule — the shift simply does not run that day.
                if (!slot) {
                  return (
                    <td key={key} className="calendar-cell is-absent">
                      <span className="visually-hidden">אין משמרת</span>
                    </td>
                  );
                }
                const short = rows.length < slot.headcount;
                return (
                  <td
                    key={key}
                    className={[
                      "calendar-cell",
                      short ? "is-short" : "",
                      over === key ? "is-over" : "",
                      cellWarnings.length ? "has-warning" : "",
                    ]
                      .filter(Boolean)
                      .join(" ")}
                    onDragOver={(event) => {
                      if (readOnly || !dragging) return;
                      // Preventing default is what marks this a valid drop
                      // target; without it the browser refuses the drop.
                      event.preventDefault();
                      setOver(key);
                    }}
                    onDragLeave={() => setOver((current) =>
                      current === key ? null : current,
                    )}
                    onDrop={(event) => {
                      event.preventDefault();
                      setOver(null);
                      if (readOnly || !dragging) return;
                      // Dropping onto the cell it came from is a no-op, not a
                      // change worth asking the manager to justify.
                      if (dragging.shift === shift && dragging.date === date) {
                        setDragging(null);
                        return;
                      }
                      onDrop?.({
                        assignment: dragging,
                        shift_name: shift,
                        slot_date: date,
                      });
                      setDragging(null);
                    }}
                  >
                    <div className="calendar-people">
                      {rows.map((row) => (
                        <Person
                          key={row.id}
                          assignment={row}
                          draggable={!readOnly}
                          onDragStart={() => setDragging(row)}
                          onDragEnd={() => {
                            setDragging(null);
                            setOver(null);
                          }}
                          blocked={isBlocked(constraints, row.employee, date, shift)}
                        />
                      ))}
                      {short ? (
                        <span className="calendar-gap">
                          חסרים {slot.headcount - rows.length}
                        </span>
                      ) : null}
                    </div>
                    {slot.is_on_call ? (
                      <span className="calendar-oncall" title="כוננות">
                        <Moon size={12} />
                      </span>
                    ) : null}
                    {cellWarnings.length ? (
                      <span
                        className="calendar-warning-dot"
                        title={cellWarnings.map((w) => w.message).join("\n")}
                      >
                        <AlertTriangle size={12} />
                      </span>
                    ) : null}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** One assigned person. The agent's reason rides along as the title, so it
 *  is always one hover away rather than hidden behind a click — under D3 the
 *  agent's judgment is final, and the reasoning is how the manager audits it. */
function Person({
  assignment,
  draggable,
  onDragStart,
  onDragEnd,
  blocked,
}: {
  assignment: Assignment;
  draggable: boolean;
  onDragStart: () => void;
  onDragEnd: () => void;
  blocked: boolean;
}) {
  return (
    <span
      className={`calendar-person${blocked ? " is-blocked" : ""}`}
      draggable={draggable}
      onDragStart={(event) => {
        // Some browsers refuse to start a drag without transfer data set.
        event.dataTransfer.setData("text/plain", assignment.id);
        event.dataTransfer.effectAllowed = "move";
        onDragStart();
      }}
      onDragEnd={onDragEnd}
      title={assignment.reason}
    >
      {assignment.employee}
    </span>
  );
}

/** The hours for a shift, read off whichever slot carries them. */
function ShiftTimes({
  slot,
  shift,
  slots,
}: {
  slot: Slot | undefined;
  shift: string;
  slots: Slot[];
}) {
  const withTimes =
    slot?.start_time
      ? slot
      : slots.find((row) => row.shift_name === shift && row.start_time);
  if (!withTimes?.start_time) return null;
  return (
    <span className="calendar-hours">
      {withTimes.start_time}–{withTimes.end_time}
    </span>
  );
}

/** Whether a recorded constraint contradicts this cell.
 *
 *  An empty `shift_name` on the constraint covers the whole day, which is the
 *  convention the interview collects and `audit.py` reads. */
function isBlocked(
  constraints: Constraint[],
  employee: string,
  date: string,
  shift: string,
): boolean {
  return constraints.some(
    (row) =>
      !row.available &&
      row.employee === employee &&
      row.constraint_date === date &&
      (row.shift_name === "" || row.shift_name === shift),
  );
}

function uniqueSorted(values: string[]): string[] {
  return Array.from(new Set(values)).sort();
}

/** Distinct values in the order they first appear. */
function uniqueByAppearance(values: string[]): string[] {
  const seen = new Set<string>();
  const ordered: string[] = [];
  for (const value of values) {
    if (seen.has(value)) continue;
    seen.add(value);
    ordered.push(value);
  }
  return ordered;
}

/** Hebrew weekday names. Hebrew here is data, not presentation — the source
 *  files and the profile both use these exact strings (D9/FILE_FORMATS). */
const HEBREW_WEEKDAYS = [
  "ראשון",
  "שני",
  "שלישי",
  "רביעי",
  "חמישי",
  "שישי",
  "שבת",
];

export function hebrewWeekday(iso: string): string {
  const date = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(date.getTime())) return "";
  return HEBREW_WEEKDAYS[date.getDay()];
}

export function formatDate(iso: string): string {
  const date = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(date.getTime())) return iso;
  return `${date.getDate()}.${date.getMonth() + 1}`;
}
