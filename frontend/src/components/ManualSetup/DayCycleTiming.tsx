"use client";

import { TimeInput } from "@/components/TimeInput";
import { nominallyHome } from "@/lib/dayCycles";
import type { DayCycle, DayCycleTiming } from "@/types";

import { Field } from "./fields";

const WEEKDAYS = ["ראשון", "שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת"];
const SHIFTS = [-3, -2, -1, 0, 1, 2, 3];
const PREVIEW_DAYS = 28;

/** Departure and return for one layer of a cycle's hours.
 *
 *  `partial` is a group's or a date's own layer: an empty choice means
 *  "as in the cycle", and only what is chosen is saved. `leaveDay` and
 *  `returnDay` are the nominal days (ISO) when an anchor exists, so the
 *  options can read "רביעי" rather than "יום לפני". */
export function TimingFields({
  value,
  onChange,
  partial = false,
  leaveDay,
  returnDay,
}: {
  value: DayCycleTiming;
  onChange: (patch: DayCycleTiming) => void;
  partial?: boolean;
  leaveDay?: string;
  returnDay?: string;
}) {
  const day = (key: "leave_day" | "return_day", nominal: string | undefined, label: string) => (
    <Field label={label}>
      <select
        value={value[key] === undefined ? "" : String(value[key])}
        onChange={(event) => onChange({ [key]: event.target.value === "" ? undefined : Number(event.target.value) })}
      >
        {partial ? <option value="">כמו במחזור</option> : null}
        {SHIFTS.map((shift) => <option key={shift} value={shift}>{dayLabel(nominal, shift)}</option>)}
      </select>
    </Field>
  );
  return (
    <div className="manual-grid rotation-window-grid">
      {day("leave_day", leaveDay, "יום היציאה הביתה")}
      <Field label={partial ? "שעת יציאה (ריק = כמו במחזור)" : "שעת יציאה (ריק = תחילת היום)"}>
        <TimeInput value={value.leave_time ?? ""} onChange={(time) => onChange({ leave_time: time })} />
      </Field>
      {day("return_day", returnDay, "יום החזרה לבסיס")}
      <Field label={partial ? "שעת חזרה (ריק = כמו במחזור)" : "שעת חזרה (ריק = תחילת היום)"}>
        <TimeInput value={value.return_time ?? ""} onChange={(time) => onChange({ return_time: time })} />
      </Field>
    </div>
  );
}

function dayLabel(nominal: string | undefined, shift: number): string {
  const relative = shift === 0 ? "ביום המעבר" : `${Math.abs(shift) === 1 ? "יום" : `${Math.abs(shift)} ימים`} ${shift < 0 ? "לפני" : "אחרי"}`;
  if (!nominal) return relative;
  const weekday = WEEKDAYS[new Date(`${addDays(nominal, shift)}T00:00:00Z`).getUTCDay()];
  return `${weekday} · ${relative}`;
}

/** Four weeks from the anchor, one row per group: the nominal days only.
 *  Hours and dated changes are applied by the server when it schedules. */
export function CyclePreview({ cycle }: { cycle: DayCycle }) {
  if (!cycle.anchor_date || cycle.base_days < 1 || cycle.home_days < 1) return null;
  const days = Array.from({ length: PREVIEW_DAYS }, (_, n) => addDays(cycle.anchor_date, n));
  return (
    <div className="day-cycle-preview" aria-label={`תצוגה מקדימה של ${cycle.name}`}>
      {cycle.groups.map((group) => (
        <div className="day-cycle-preview-row" key={group}>
          <strong>{group}׳</strong>
          <ol>
            {days.map((iso, n) => {
              const home = nominallyHome(cycle, group, n);
              const weekday = new Date(`${iso}T00:00:00Z`).getUTCDay();
              return (
                <li key={iso} className={home ? "is-home" : undefined} title={`${iso.slice(8)}/${iso.slice(5, 7)} · ${home ? "בבית" : "בבסיס"}`}>
                  {WEEKDAYS[weekday][0]}
                </li>
              );
            })}
          </ol>
        </div>
      ))}
      <p className="rotation-hint">מסומן = בבית. שעות היציאה והחזרה והשינויים לפי תאריך נאכפים בשיבוץ.</p>
    </div>
  );
}

export function addDays(iso: string, days: number): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!match) return "";
  return new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3]) + days)).toISOString().slice(0, 10);
}
