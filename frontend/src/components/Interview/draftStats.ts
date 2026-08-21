/** What the draft profile adds up to, computed in the browser.
 *
 *  The interview returns the draft on every turn, and until now the panel
 *  beside the conversation rendered three array lengths from it. Those are
 *  the cheapest facts in the profile and not the ones a manager is actually
 *  checking: whether the shifts they just described are staffable by the
 *  people they just listed is arithmetic, and it is the arithmetic that
 *  tells them they have under-hired before the scheduler does.
 *
 *  **Pure functions over the draft. No model call, ever** — the same line
 *  `bl/audit.py` holds on the backend (D3). A model asked "how many people
 *  do these shifts need" is doing arithmetic by generation, and a wrong
 *  answer looks exactly like a right one. Everything here is countable from
 *  the draft, so it is counted.
 *
 *  This mirrors no backend endpoint on purpose. The numbers are a *reading*
 *  of the draft the server already sent, so they need no round-trip and land
 *  the instant a turn does. `bl/audit.py` stays the authority once there is a
 *  real schedule to audit; this is the pre-schedule view, over a profile that
 *  is still half-written and therefore full of absent fields.
 *
 *  Every field is treated as possibly missing, wrongly typed, or half-filled,
 *  because during an interview it usually is. Nothing here throws on a
 *  malformed draft — a panel that crashes on turn three is worse than one
 *  showing a zero.
 */

import type { WorkplaceProfile } from "@/types";

/** A shift as the interview drafts one. Every field optional: the model
 *  fills these in across several turns, so a shift with a name and no hours
 *  is a normal intermediate state, not an error. */
interface DraftShift {
  name?: unknown;
  start_time?: unknown;
  end_time?: unknown;
  days?: unknown;
  staffing?: unknown;
  is_on_call?: unknown;
  hour_weight?: unknown;
}

interface DraftStaffing {
  days?: unknown;
  headcount?: unknown;
  required_roles?: unknown;
}

interface DraftEmployee {
  name?: unknown;
  is_trainee?: unknown;
  counts_toward_staffing?: unknown;
  is_casual?: unknown;
  is_shift_manager?: unknown;
}

export interface DraftStats {
  /** People who count toward filling a slot. A trainee on a shadow shift is
   *  present at work and still leaves the slot needing somebody else, so the
   *  two are counted apart rather than summed into a headline that reads as
   *  more coverage than exists. */
  staff: number;
  trainees: number;
  casuals: number;
  managers: number;
  shifts: number;
  onCallShifts: number;
  rules: number;
  hardRules: number;
  /** Slots a week, summed over each shift's own per-day staffing. */
  weeklySlots: number;
  /** Paid hours a week implied by those slots, on-call weighted by
   *  `hour_weight` when the manager gave one. */
  weeklyHours: number;
  /** Weekly hours per counted employee — the number that says whether this
   *  roster can carry this schedule at all. Null while either side is
   *  unknown, so the panel omits it rather than showing a division by zero
   *  dressed up as a fact. */
  hoursPerEmployee: number | null;
  /** How many of the shifts drafted so far have complete-enough hours to be
   *  costed. The hours figure is a floor while this is below `shifts`. */
  shiftsWithHours: number;
  /** Whether every shift so far has been costed. When false, `weeklyHours`
   *  is a partial total and the UI says so instead of implying precision. */
  hoursComplete: boolean;
}

export function computeDraftStats(
  draft: WorkplaceProfile | null | undefined,
): DraftStats {
  const employees = asArray<DraftEmployee>(draft?.employees);
  const shifts = asArray<DraftShift>(draft?.shifts);
  const rules = asArray<{ priority?: unknown }>(draft?.rules);

  // A trainee is excluded from staffing by default because that is what a
  // shadow shift means, but the interview asks the question explicitly and
  // the answer wins when it is there. `counts_toward_staffing` is therefore
  // read first, and the trainee flag is only the fallback.
  const counted = employees.filter(countsTowardStaffing);
  const trainees = employees.filter((person) => isTrue(person.is_trainee));

  let weeklySlots = 0;
  let weeklyHours = 0;
  let shiftsWithHours = 0;

  for (const shift of shifts) {
    const slots = weeklySlotsFor(shift);
    weeklySlots += slots;
    const hours = shiftLengthHours(shift);
    if (hours === null) continue;
    shiftsWithHours += 1;
    // An on-call night may be paid or counted differently from a worked
    // shift; the interview collects `hour_weight` for exactly this, so it is
    // applied rather than assumed to be 1 (bl/audit.py holds the same rule).
    weeklyHours += slots * hours * hourWeight(shift);
  }

  const staff = counted.length;
  return {
    staff,
    trainees: trainees.length,
    casuals: employees.filter((person) => isTrue(person.is_casual)).length,
    managers: employees.filter((person) => isTrue(person.is_shift_manager))
      .length,
    shifts: shifts.length,
    onCallShifts: shifts.filter((shift) => isTrue(shift.is_on_call)).length,
    rules: rules.length,
    hardRules: rules.filter((rule) => rule?.priority === "hard").length,
    weeklySlots,
    weeklyHours: round(weeklyHours),
    hoursPerEmployee:
      staff > 0 && weeklyHours > 0 ? round(weeklyHours / staff) : null,
    shiftsWithHours,
    hoursComplete: shifts.length > 0 && shiftsWithHours === shifts.length,
  };
}

/** Slots a week for one shift, summed across its staffing groups.
 *
 *  Headcount routinely differs between midweek and weekend, which is why the
 *  profile holds a list of `{days, headcount}` rather than one number. Each
 *  group contributes `headcount × its own day count`; flattening to an
 *  average would understate a week that is heavy at one end.
 *
 *  With no staffing recorded yet, the shift still occupies its days — one
 *  person is the floor, so a newly named shift shows as costing something
 *  rather than as free until its staffing turn arrives.
 */
function weeklySlotsFor(shift: DraftShift): number {
  const groups = asArray<DraftStaffing>(shift.staffing);
  const shiftDays = asStrings(shift.days).length;

  if (groups.length === 0) return shiftDays;

  let slots = 0;
  for (const group of groups) {
    const headcount = asNumber(group.headcount);
    if (headcount === null) continue;
    // A group naming no days is read as covering the shift's own days —
    // the common shape when a shift runs a uniform week and the model
    // recorded one entry without repeating the day list.
    const days = asStrings(group.days).length || shiftDays;
    slots += headcount * days;
  }
  return slots;
}

/** One shift's length in hours, or null when its times are not usable yet.
 *
 *  An end at or before the start crosses midnight and is normal — the
 *  interview prompt says so explicitly and forbids swapping the times — so
 *  it wraps a day rather than reading as negative. A zero-length result is
 *  refused: a shift from 08:00 to 08:00 is far more likely to be a
 *  half-typed answer than a genuine 24-hour one, and inventing 24 hours
 *  there would overstate the week by a whole shift.
 */
function shiftLengthHours(shift: DraftShift): number | null {
  const start = minutesOf(shift.start_time);
  const end = minutesOf(shift.end_time);
  if (start === null || end === null) return null;
  const span = end > start ? end - start : end + 24 * 60 - start;
  if (span <= 0) return null;
  return span / 60;
}

function minutesOf(value: unknown): number | null {
  if (typeof value !== "string") return null;
  const match = /^(\d{1,2}):(\d{2})$/.exec(value.trim());
  if (!match) return null;
  const hours = Number(match[1]);
  const minutes = Number(match[2]);
  if (hours > 23 || minutes > 59) return null;
  return hours * 60 + minutes;
}

/** How much one worked hour of this shift counts toward the total.
 *
 *  Defaults to 1 — a shift worked in full — and only a weight the manager
 *  actually stated moves it. A zero is honoured: an unpaid on-call standby
 *  really can weigh nothing toward hours.
 */
function hourWeight(shift: DraftShift): number {
  const weight = asNumber(shift.hour_weight);
  return weight === null || weight < 0 ? 1 : weight;
}

function countsTowardStaffing(person: DraftEmployee): boolean {
  if (typeof person?.counts_toward_staffing === "boolean") {
    return person.counts_toward_staffing;
  }
  return !isTrue(person?.is_trainee);
}

function isTrue(value: unknown): boolean {
  return value === true;
}

function asArray<T>(value: unknown): T[] {
  return Array.isArray(value) ? (value.filter(isObject) as T[]) : [];
}

function isObject(value: unknown): boolean {
  return typeof value === "object" && value !== null;
}

function asStrings(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter(
    (item): item is string => typeof item === "string" && item.trim() !== "",
  );
}

function asNumber(value: unknown): number | null {
  if (typeof value !== "number" || !Number.isFinite(value)) return null;
  return value;
}

/** One decimal place. Hours land on halves and quarters often enough that
 *  rounding to whole numbers loses a real distinction, and a long float in a
 *  stat tile reads as noise. */
function round(value: number): number {
  return Math.round(value * 10) / 10;
}
