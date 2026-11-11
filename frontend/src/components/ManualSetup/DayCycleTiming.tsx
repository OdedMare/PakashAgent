"use client";

import { TimeInput } from "@/components/TimeInput";
import type { DayCycleTiming } from "@/types";

import { Field } from "./fields";

const WEEKDAYS = ["ראשון", "שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת"];
const SHIFTS = [-3, -2, -1, 0, 1, 2, 3];

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

export function addDays(iso: string, days: number): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!match) return "";
  return new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3]) + days)).toISOString().slice(0, 10);
}
