"use client";

import { AlertTriangle, Moon, Plus, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import type {
  Assignment,
  Constraint,
  Schedule,
  ScheduleWarning,
  Slot,
} from "@/types";
import { displayDate } from "@/components/DateInput";
import { constraintBlocksSlot } from "@/lib/constraints";

import { buildPalette, colorStyle } from "./palette";

/** The living schedule as a grid, right-to-left.
 *
 *  Two gestures write, and they are deliberately not the same gesture:
 *
 *  - **Dragging an assignment does not edit anything.** The drop opens a
 *    confirmation that collects the manager's reason, and only that dialog
 *    writes ([D12](../../../docs/DECISIONS.md#d12--dragging-a-shift-is-a-proposal-not-an-edit)).
 *    A drag moves somebody who is already placed — it takes a shift away
 *    from one person and hands it to another, and that is a change somebody
 *    is owed an account of.
 *  - **Filling an empty cell writes immediately** (D18). It takes nothing
 *    away from anybody, so there is no one for a reason to be owed to, and
 *    asking for a justification per cell would make authoring a week by hand
 *    cost a dialog per shift. The boss may build a schedule without the
 *    agent being involved at all.
 *
 *  Every person carries a colour drawn from the roster, so a week reads as a
 *  shape before it reads as text — "is anyone on five days running" is
 *  answerable without parsing a single name. Provenance is marked too: a
 *  chip the manager placed is dotted, one the agent generated is not, which
 *  is what makes a hand-built week distinguishable from a generated one
 *  after the fact.
 *
 *  Warnings are painted onto the cells they belong to and never prevent a
 *  drop or an assignment ([D3](../../../docs/DECISIONS.md#d3--the-agent-decides-code-only-audits-)).
 *  A cell can be short-staffed, double-booked, and still perfectly editable:
 *  the manager is the one who decides, and the grid only has to tell them. */
export function Calendar({
  schedule,
  constraints,
  employees = [],
  readOnly = false,
  dark = false,
  onDrop,
  onAssign,
  onUnassign,
}: {
  schedule: Schedule;
  constraints: Constraint[];
  /** The roster, in profile order — what the colours are assigned from. */
  employees?: string[];
  readOnly?: boolean;
  dark?: boolean;
  onDrop?: (move: {
    assignment: Assignment;
    shift_name: string;
    slot_date: string;
  }) => void;
  /** Fill an empty cell. Writes immediately (D18). */
  onAssign?: (input: { shift_name: string; slot_date: string; employee: string }) => void;
  /** Clear one person off a cell. */
  onUnassign?: (assignment: Assignment) => void;
}) {
  const [dragging, setDragging] = useState<Assignment | null>(null);
  const [over, setOver] = useState<string | null>(null);
  // Which empty cell has its employee picker open, as `shift|date`. One at a
  // time: two open pickers would let the manager start two assignments and
  // lose track of which cell the next click lands in.
  const [picking, setPicking] = useState<string | null>(null);

  const dates = uniqueSorted(schedule.slots.map((slot) => slot.slot_date));
  // Shift rows keep the order the vocabulary gave them, by first appearance,
  // rather than being sorted alphabetically — a workplace's shifts have a
  // natural order (morning, then evening, then on-call) that alphabetising
  // would scramble.
  const shifts = uniqueByAppearance(
    schedule.slots.map((slot) => slot.shift_name),
  );

  // Colours come from the roster's own order, so ten people get ten distinct
  // hues. Names on the grid that the roster no longer carries still get a
  // stable colour — see `buildPalette`.
  const hueOf = useMemo(() => buildPalette(employees), [employees]);

  const editable = !readOnly && Boolean(onAssign);

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
              <th
                key={date}
                scope="col"
                className={isWeekend(date) ? "is-weekend" : undefined}
              >
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
                // How short this cell is, taken from the audit's own count
                // rather than recomputed from the cards.
                //
                // This grid renders on the member and employee surfaces,
                // which hold no roster — a share link carries no identity
                // (D10), so there is nothing here that could tell a trainee
                // shadowing the shift from one of the people it asked for.
                // Counting the cards would therefore report a cell covered
                // that the manager's board calls short, and the audit's
                // `unfilled` warning is already on the cell carrying the
                // number `bl/audit.py` worked out. No warning means no
                // shortage — including on a shift whose headcount nobody
                // ever stated, where inventing one would be fiction.
                const missing = missingFrom(cellWarnings, shift, date);
                const short = missing > 0;
                return (
                  <td
                    key={key}
                    className={[
                      "calendar-cell",
                      short ? "is-short" : "",
                      over === key ? "is-over" : "",
                      cellWarnings.length ? "has-warning" : "",
                      isWeekend(date) ? "is-weekend" : "",
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
                          hue={hueOf(row.employee)}
                          dark={dark}
                          draggable={!readOnly}
                          removable={editable && Boolean(onUnassign)}
                          onRemove={() => onUnassign?.(row)}
                          onDragStart={() => setDragging(row)}
                          onDragEnd={() => {
                            setDragging(null);
                            setOver(null);
                          }}
                          blocked={constraintBlocksSlot(
                            constraints, row.employee, date, slot,
                          )}
                        />
                      ))}
                      {short ? (
                        <span className="calendar-gap">חסרים {missing}</span>
                      ) : null}
                      {/* D18: the manual path. Present on every editable
                          cell rather than only on empty ones — a slot that
                          wants two people is still short with one on it. */}
                      {editable ? (
                        picking === key ? (
                          <EmployeePicker
                            employees={employees}
                            taken={rows.map((row) => row.employee)}
                            hueOf={hueOf}
                            dark={dark}
                            onPick={(employee) => {
                              setPicking(null);
                              onAssign?.({
                                shift_name: shift,
                                slot_date: date,
                                employee,
                              });
                            }}
                            onClose={() => setPicking(null)}
                          />
                        ) : (
                          <button
                            type="button"
                            className="calendar-add"
                            onClick={() => setPicking(key)}
                            aria-label={`שיבוץ ל${shift} ב-${formatDate(date)}`}
                            title="שיבוץ ידני"
                          >
                            <Plus size={13} />
                          </button>
                        )
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

/** One assigned person, in their own colour.
 *
 *  The agent's reason rides along as the title, so it is always one hover
 *  away rather than hidden behind a click — under D3 the agent's judgment is
 *  final, and the reasoning is how the manager audits it.
 *
 *  A chip the manager placed by hand is marked (D18). Not as a warning —
 *  there is nothing wrong with it — but because "did I put this here or did
 *  the agent" is exactly the question a half-generated, half-edited week
 *  raises, and the reason text alone answers it only if you stop to read. */
function Person({
  assignment,
  hue,
  dark,
  draggable,
  removable,
  onRemove,
  onDragStart,
  onDragEnd,
  blocked,
}: {
  assignment: Assignment;
  hue: number;
  dark: boolean;
  draggable: boolean;
  removable: boolean;
  onRemove: () => void;
  onDragStart: () => void;
  onDragEnd: () => void;
  blocked: boolean;
}) {
  const manual = assignment.source === "manager";
  return (
    <span
      className={[
        "calendar-person",
        blocked ? "is-blocked" : "",
        manual ? "is-manual" : "",
      ]
        .filter(Boolean)
        .join(" ")}
      // The colour is per-name and computed at render, so it cannot be a
      // class. `is-blocked` overrides it in CSS — a constraint conflict has
      // to out-shout a decorative hue.
      style={blocked ? undefined : colorStyle(hue, dark)}
      draggable={draggable}
      onDragStart={(event) => {
        // Some browsers refuse to start a drag without transfer data set.
        event.dataTransfer.setData("text/plain", assignment.id);
        event.dataTransfer.effectAllowed = "move";
        onDragStart();
      }}
      onDragEnd={onDragEnd}
      title={
        manual
          ? `${assignment.employee} — שובץ ידנית. ${assignment.reason}`
          : assignment.reason
      }
    >
      {assignment.employee}
      {removable ? (
        <button
          type="button"
          className="calendar-person-remove"
          // The chip is draggable; without this the button press starts a
          // drag instead of a click on some browsers.
          draggable={false}
          onDragStart={(event) => event.preventDefault()}
          onClick={(event) => {
            event.stopPropagation();
            onRemove();
          }}
          aria-label={`הסרת ${assignment.employee}`}
          title="הסרה מהמשמרת"
        >
          <X size={11} />
        </button>
      ) : null}
    </span>
  );
}

/** Choose who goes into a cell.
 *
 *  Lists the whole roster rather than filtering to who is "available": the
 *  audit reports conflicts and never blocks (D3), so hiding a person here
 *  would be the grid quietly enforcing what the product decided not to
 *  enforce. Somebody already on this slot is dropped, because assigning them
 *  twice conflicts silently server-side and would look like nothing
 *  happened. */
function EmployeePicker({
  employees,
  taken,
  hueOf,
  dark,
  onPick,
  onClose,
}: {
  employees: string[];
  taken: string[];
  hueOf: (name: string) => number;
  dark: boolean;
  onPick: (employee: string) => void;
  onClose: () => void;
}) {
  const box = useRef<HTMLDivElement | null>(null);
  // Opening downward off the bottom of the grid would clip the list: the
  // calendar scrolls horizontally, and a box with `overflow-x: auto` clips
  // vertically on the other axis too.
  //
  // The test is *which side has more room*, not "does it fit below" — on a
  // three-row grid a full roster fits below almost nowhere, so the latter
  // flips every picker including the top row's, where flipping puts it
  // further out than leaving it. Measured after mount, because how much room
  // there is depends on the viewport rather than on the row index.
  const [flip, setFlip] = useState(false);

  useEffect(() => {
    const element = box.current;
    const scroller = element?.closest(".calendar-scroll");
    const cell = element?.closest("td");
    if (!element || !scroller || !cell) return;
    const frame = scroller.getBoundingClientRect();
    const anchor = cell.getBoundingClientRect();
    const room = element.getBoundingClientRect().height;
    const below = frame.bottom - anchor.bottom;
    const above = anchor.top - frame.top;
    if (below < room && above > below) setFlip(true);
  }, []);

  // Close on outside click and on Escape. Without both, a picker opened by
  // mistake can only be dismissed by choosing somebody — which is a write.
  useEffect(() => {
    const onDown = (event: MouseEvent) => {
      if (!box.current?.contains(event.target as Node)) onClose();
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [onClose]);

  const options = employees.filter((name) => !taken.includes(name));

  return (
    <div
      className={`calendar-picker${flip ? " is-flipped" : ""}`}
      ref={box}
      role="dialog"
      aria-label="בחירת עובד"
    >
      {options.length ? (
        options.map((name) => (
          <button
            key={name}
            type="button"
            className="calendar-picker-option"
            style={colorStyle(hueOf(name), dark)}
            onClick={() => onPick(name)}
          >
            {name}
          </button>
        ))
      ) : (
        <span className="calendar-picker-empty">כל הצוות כבר משובץ</span>
      )}
    </div>
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

/** How many people this cell is short, per the audit that produced it.
 *
 *  `bl/audit.py` writes `{assigned, required}` into an `unfilled` warning's
 *  `details`, having already decided which of the people on the cell fill one
 *  of its seats and how many seats this date's slot asks for. Both of those
 *  are facts this grid cannot see: it holds no roster, and the per-weekday
 *  staffing that makes a Friday need ten where a Tuesday needs four lives in
 *  the profile. So the number is read, not recomputed.
 *
 *  Whole-day warnings (`shift === ""`) reach this cell too and are skipped:
 *  they are about the date, not about this shift's staffing.
 */
function missingFrom(
  warnings: ScheduleWarning[],
  shift: string,
  date: string,
): number {
  for (const warning of warnings) {
    if (warning.code !== "unfilled") continue;
    if (warning.shift !== shift || warning.date !== date) continue;
    const required = Number(warning.details?.required);
    const assigned = Number(warning.details?.assigned);
    if (!Number.isFinite(required) || !Number.isFinite(assigned)) continue;
    return Math.max(0, required - assigned);
  }
  return 0;
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

/** Friday and Saturday — the Israeli weekend, tinted so a week reads at a
 *  glance. Presentation only: nothing in the audit or the profile treats
 *  these days differently, and a workplace whose shifts run through the
 *  weekend still shows them exactly as declared. */
export function isWeekend(iso: string): boolean {
  const date = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(date.getTime())) return false;
  return date.getDay() === 5 || date.getDay() === 6;
}

export function formatDate(iso: string): string {
  return displayDate(iso);
}
