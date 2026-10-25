"use client";

import { CalendarPlus, CalendarRange, Layers, Plus, Trash2, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { DateInput, displayDate } from "@/components/DateInput";
import { hebrewWeekday } from "@/components/Management/Calendar";
import type { RequiredAssignment, Schedule } from "@/types";

import { addDays, sundayOf } from "./dates";

type Row = RequiredAssignment & { id: number };

/** Ask the agent for a run of days.
 *
 *  One dialog for both places a build starts. On a week with nothing stored
 *  it opens a period; handed a `period`, it builds inside that draft instead
 *  — "from this day until Saturday, or until the day I choose". The second
 *  takes no list of required shifts, because the board behind it already is
 *  one: whatever the manager placed by hand is kept and filled around (D18).
 *
 *  Either way the build can be narrowed to some shift types — "only the
 *  nights for the month". Rows on every other shift stay as they are; the
 *  names come from setup, never from this file (D9).
 */
export function GenerateDialog({
  employees,
  shifts,
  from,
  through,
  period = null,
  busy,
  onConfirm,
  onCancel,
}: {
  employees: string[];
  shifts: Record<string, unknown>[];
  /** The run the dialog opens on. Both ends stay editable. */
  from: string;
  through: string;
  /** The draft being built into, when there is one. Its dates bound the
   *  run: a build is one job on one period, and a run that spilled past it
   *  would have nowhere to write the days beyond. */
  period?: Schedule | null;
  busy: boolean;
  onConfirm: (input: {
    starts_on: string;
    ends_on: string;
    instructions: string;
    required_assignments: RequiredAssignment[];
    /** Only these shift types; empty means every shift. */
    shifts: string[];
  }) => void;
  onCancel: () => void;
}) {
  const [startsOn, setStartsOn] = useState(from);
  const [endsOn, setEndsOn] = useState(through);
  const [instructions, setInstructions] = useState("");
  const dates = useMemo(
    () => dateRange(startsOn, endsOn),
    [startsOn, endsOn],
  );
  const options = useMemo(() => shiftOptions(shifts), [shifts]);
  // Empty is "every shift", the default; a choice narrows the build to it.
  const [chosen, setChosen] = useState<string[]>([]);
  const toggleShift = (name: string) =>
    setChosen((current) =>
      current.includes(name)
        ? current.filter((item) => item !== name)
        : [...current, name],
    );
  const built = chosen.length
    ? options.filter((option) => chosen.includes(option.name))
    : options;
  const runsInRange = dates.some((date) => shiftsForDate(built, date).length > 0);
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
  const valid = validRange && runsInRange && rows.every(
    (row) => row.employee && dates.includes(row.date) && row.shift,
  );

  const presets = useMemo(
    () => rangePresets(startsOn, period?.ends_on),
    [startsOn, period?.ends_on],
  );
  // What the run would do to days that already hold something. Counted from
  // the period on screen rather than asked for: it is the same rule the
  // server applies — the manager's rows stay, everything else is replaced.
  const standing = useMemo(() => {
    const rows = (period?.assignments ?? []).filter(
      (row) => row.date >= startsOn && row.date <= endsOn
        && (!chosen.length || chosen.includes(row.shift)),
    );
    const kept = rows.filter((row) => row.source === "manager").length;
    return { kept, replaced: rows.length - kept };
  }, [period, startsOn, endsOn, chosen]);

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
            <CalendarPlus size={17} />{" "}
            {period ? "בניית ימים בסידור הקיים" : "בניית סידור לתאריך או לטווח"}
          </h2>
          <button type="button" className="icon-button" onClick={onCancel} aria-label="סגירה">
            <X size={17} />
          </button>
        </header>

        <p className="modal-summary">
          {period
            ? "בחרו מאיזה יום ועד איזה יום לבנות. הסוכן יבנה רק את הימים האלה ויתחשב בכל מה שכבר נקבע בשאר הסידור."
            : "בחרו טווח, הוסיפו כללים לבקשה, ואם צריך גם שיבוצים שחייבים להופיע. הסוכן יבנה כל יום בנפרד ויתחשב בכל מה שכבר נקבע."}
        </p>

        <form onSubmit={(event) => {
          event.preventDefault();
          if (valid && !busy) {
            onConfirm({
              starts_on: startsOn,
              ends_on: endsOn,
              instructions: instructions.trim(),
              required_assignments: rows.map(({ employee, shift, date }) => ({ employee, shift, date })),
              shifts: chosen,
            });
          }
        }}>
          <section className="generate-period" aria-labelledby="generate-period-title">
            <div className="generate-period-head">
              <span className="generate-period-mark" aria-hidden="true">
                <CalendarRange size={18} />
              </span>
              <div>
                <h3 id="generate-period-title">לאיזו תקופה לבנות?</h3>
                <p>אפשר לבחור קיצור דרך ואז לדייק את התאריכים.</p>
              </div>
            </div>

            <div className="generate-range-presets" aria-label="אורך התקופה">
              {presets.map((preset) => (
                <button
                  key={preset.label}
                  type="button"
                  className={endsOn === preset.end ? "is-active" : ""}
                  aria-pressed={endsOn === preset.end}
                  onClick={() => setEndsOn(preset.end)}
                >
                  {preset.label}
                </button>
              ))}
            </div>

            <div className="generate-date-fields">
              <label>
                <span>מתאריך</span>
                <DateInput
                  min={period?.starts_on}
                  max={period?.ends_on}
                  value={startsOn}
                  onChange={(next) => {
                    setStartsOn(next);
                    if (endsOn < next) setEndsOn(next);
                  }}
                  required
                />
              </label>
              <span className="generate-date-connector" aria-hidden="true">עד</span>
              <label>
                <span>עד תאריך</span>
                <DateInput
                  min={startsOn}
                  max={period?.ends_on}
                  value={endsOn}
                  onChange={setEndsOn}
                  required
                />
              </label>
            </div>

            <div className="generate-range-summary" aria-live="polite">
              <strong>{dates.length === 1 ? "יום אחד" : `${dates.length} ימים`}</strong>
              <span>
                {hebrewWeekday(startsOn)} {displayDate(startsOn)}
                {dates.length > 1 ? ` — ${hebrewWeekday(endsOn)} ${displayDate(endsOn)}` : ""}
              </span>
            </div>
          </section>

          {options.length > 1 ? (
            <section className="generate-shifts" aria-labelledby="generate-shifts-title">
              <div className="generate-period-head">
                <span className="generate-period-mark" aria-hidden="true">
                  <Layers size={18} />
                </span>
                <div>
                  <h3 id="generate-shifts-title">אילו משמרות לשבץ?</h3>
                  <p>אפשר לשבץ רק סוג משמרת אחד או כמה. שאר המשמרות נשארות כמו שהן.</p>
                </div>
              </div>
              <div className="generate-shift-choices" role="group" aria-label="סוגי משמרות">
                <button
                  type="button"
                  className={chosen.length ? "" : "is-active"}
                  aria-pressed={!chosen.length}
                  onClick={() => setChosen([])}
                >
                  כל המשמרות
                </button>
                {options.map((option) => (
                  <button
                    key={option.name}
                    type="button"
                    className={chosen.includes(option.name) ? "is-active" : ""}
                    aria-pressed={chosen.includes(option.name)}
                    onClick={() => toggleShift(option.name)}
                  >
                    רק {option.name}
                    {option.hours ? <small>{option.hours}</small> : null}
                  </button>
                ))}
              </div>
              {chosen.length && validRange && !runsInRange ? (
                <p className="generate-shifts-empty" role="alert">
                  המשמרות שנבחרו לא מתקיימות בימים האלה.
                </p>
              ) : null}
            </section>
          ) : null}

          <label className="generate-instructions">
            <span>הנחיות מיוחדות לתקופה הזאת <small>לא חובה</small></span>
            <textarea
              value={instructions}
              maxLength={2000}
              placeholder="לדוגמה: השבוע להעדיף את דנה בבקרים"
              onChange={(event) => setInstructions(event.target.value)}
            />
          </label>
          {period ? (
            <p className="modal-note">
              {chosen.length
                ? `רק ${chosen.join(", ")} ייבנו מחדש. שאר המשמרות בימים האלה נשארות כמו שהן. `
                : ""}
              {standing.replaced
                ? `${standing.replaced} שיבוצים שנבנו בימים האלה יוחלפו. `
                : ""}
              {standing.kept
                ? `${standing.kept} שיבוצים ששיבצתם ידנית נשארים במקומם, והסוכן ימלא סביבם.`
                : "מה שתשבצו ידנית על הלוח נשאר במקומו, והסוכן ממלא סביבו."}
            </p>
          ) : null}
          {period ? null : (
            <>
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
                          {hebrewWeekday(date)} · {displayDate(date)}
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
            </>
          )}

          <p className="modal-hint">
            טווח הבנייה: {hebrewWeekday(startsOn)} {displayDate(startsOn)} עד {hebrewWeekday(endsOn)} {displayDate(endsOn)}. כללי מקום העבודה והאילוצים הקיימים חלים על כל יום.
            {!period && validRange && !fillsItsWeeks(startsOn, endsOn)
              ? " שאר ימי השבוע ייפתחו ריקים — לשיבוץ ידני או לבנייה בהמשך."
              : ""}
          </p>
          <div className="modal-actions">
            <button type="button" className="ghost-button" onClick={onCancel}>ביטול</button>
            <button type="submit" className="primary-button" disabled={!valid || busy}>
              {busy
                ? "בונה…"
                : `${chosen.length ? `שיבוץ רק ${chosen.join(", ")}` : "בניית הסידור"} ${
                    dates.length === 1 ? "ליום" : `ל-${dates.length} ימים`
                  }`}
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

/** The shortcuts for where a run ends, given where it starts.
 *
 *  "עד שבת" is the one a manager reaches for mid-week: the rest of this
 *  week, whatever day it is. Inside a period the weeks-long ones give way to
 *  the period's own end, and any two that land on the same date are offered
 *  once — from a Sunday, "until Saturday" *is* the week. */
function rangePresets(
  start: string,
  limit?: string,
): { label: string; end: string }[] {
  const saturday = addDays(sundayOf(start), 6);
  const offered = [
    { label: "יום אחד", end: start },
    { label: "עד שבת", end: saturday },
    ...(limit
      ? [{ label: "עד סוף הסידור", end: limit }]
      : [
          { label: "שבוע", end: addDays(start, 6) },
          { label: "שבועיים", end: addDays(start, 13) },
        ]),
  ];
  const seen = new Set<string>();
  return offered.filter((preset) => {
    if ((limit && preset.end > limit) || seen.has(preset.end)) return false;
    seen.add(preset.end);
    return true;
  });
}

/** Whether a run is whole weeks, Sunday through Saturday. */
function fillsItsWeeks(first: string, last: string): boolean {
  return sundayOf(first) === first && addDays(sundayOf(last), 6) === last;
}

function dateRange(first: string, last: string): string[] {
  const dates: string[] = [];
  const iso = /^\d{4}-\d{2}-\d{2}$/;
  if (!iso.test(first) || !iso.test(last)) return dates;
  for (let cursor = first; cursor <= last; cursor = addDays(cursor, 1)) dates.push(cursor);
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
