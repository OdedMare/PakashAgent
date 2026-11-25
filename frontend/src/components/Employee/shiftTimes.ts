import type { EmployeeView, PersonalShift } from "@/types";

/** One of this person's shifts, placed on the clock.
 *
 *  `start`/`end` are local times. A shift whose end is not after its start
 *  (a night, 23:00–07:00) ends the next morning. With no hours known at all
 *  the shift spans its whole date and `startTime` is empty, so the screen
 *  shows no hours rather than invented ones. */
export interface TimedShift extends PersonalShift {
  start: Date;
  end: Date;
  startTime: string;
  endTime: string;
  with: string[];
}

/** This person's shifts with their hours and who else is on them, in order.
 *
 *  Hours come from the published slot first — that is what the week was
 *  built with, including a day whose hours the manager changed — and from
 *  the profile's shift vocabulary only when the slot does not say (D9: the
 *  names and hours are per-workplace data, never a literal here). */
export function timedShifts(view: EmployeeView): TimedShift[] {
  const slotHours = new Map<string, [string, string]>();
  for (const slot of view.schedule?.slots ?? []) {
    slotHours.set(`${slot.slot_date}|${slot.shift_name}`, [slot.start_time, slot.end_time]);
  }
  const profileHours = new Map<string, [string, string]>();
  for (const raw of Array.isArray(view.shifts) ? view.shifts : []) {
    const row = raw as { name?: unknown; start_time?: unknown; end_time?: unknown };
    if (typeof row.name === "string") {
      profileHours.set(row.name, [String(row.start_time ?? ""), String(row.end_time ?? "")]);
    }
  }
  const withMe = new Map(view.teammates.map((row) => [`${row.date}|${row.shift}`, row.with]));

  return view.summary.shifts
    .map((shift) => {
      const key = `${shift.date}|${shift.shift}`;
      const [startTime, endTime] = slotHours.get(key) ?? profileHours.get(shift.shift) ?? ["", ""];
      return place(shift, hhmm(startTime), hhmm(endTime), withMe.get(key) ?? []);
    })
    .sort((a, b) => a.start.getTime() - b.start.getTime());
}

/** Where `now` falls among the shifts: the one under way, the next to
 *  start, and the rest split into still-ahead and already-over. */
export function splitByNow(shifts: TimedShift[], now: Date) {
  const t = now.getTime();
  const current = shifts.find((s) => s.start.getTime() <= t && t < s.end.getTime());
  const ahead = shifts.filter((s) => s.start.getTime() > t);
  return {
    current,
    next: ahead[0],
    upcoming: shifts.filter((s) => s.end.getTime() > t),
    past: shifts.filter((s) => s.end.getTime() <= t),
  };
}

/** "בעוד 20 דקות", "היום, בעוד 3 שעות", "מחר", "בעוד 4 ימים". */
export function untilLabel(start: Date, now: Date): string {
  const minutes = Math.max(0, Math.round((start.getTime() - now.getTime()) / 60000));
  if (minutes < 60) return minutes <= 1 ? "בעוד דקה" : `בעוד ${minutes} דקות`;
  const days = calendarDaysBetween(now, start);
  if (days === 0) {
    const hours = Math.round(minutes / 60);
    return hours === 1 ? "היום, בעוד שעה" : hours === 2 ? "היום, בעוד שעתיים" : `היום, בעוד ${hours} שעות`;
  }
  if (days === 1) return "מחר";
  if (days === 2) return "בעוד יומיים";
  return `בעוד ${days} ימים`;
}

/** "07:00–15:00", or empty when the hours are not known. */
export function hoursLabel(shift: TimedShift): string {
  return shift.startTime && shift.endTime ? `${shift.startTime}–${shift.endTime}` : "";
}

function place(shift: PersonalShift, startTime: string, endTime: string, others: string[]): TimedShift {
  const [y, m, d] = shift.date.split("-").map(Number);
  if (!startTime) {
    return {
      ...shift, startTime: "", endTime: "", with: others,
      start: new Date(y, m - 1, d), end: new Date(y, m - 1, d + 1),
    };
  }
  const [sh, sm] = startTime.split(":").map(Number);
  const [eh, em] = (endTime || startTime).split(":").map(Number);
  const start = new Date(y, m - 1, d, sh, sm);
  const end = new Date(y, m - 1, d, eh, em);
  if (end.getTime() <= start.getTime()) end.setDate(end.getDate() + 1);
  return { ...shift, startTime, endTime: endTime || "", start, end, with: others };
}

/** "07:00:00" and "7:00" both read as "07:00"; anything else as unknown. */
function hhmm(value: string): string {
  const match = /^(\d{1,2}):(\d{2})/.exec(value || "");
  return match ? `${match[1].padStart(2, "0")}:${match[2]}` : "";
}

function calendarDaysBetween(from: Date, to: Date): number {
  const a = new Date(from.getFullYear(), from.getMonth(), from.getDate());
  const b = new Date(to.getFullYear(), to.getMonth(), to.getDate());
  return Math.round((b.getTime() - a.getTime()) / 86400000);
}
