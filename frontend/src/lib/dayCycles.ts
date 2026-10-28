import type { DayCycle } from "@/types";

/** Day-based cycles as the setup screens name them.
 *
 *  The arithmetic of who is home on which date lives in the server
 *  (`bl/rotation/day_cycles.py`); the only date math here is the setup
 *  preview, the same way the weekend cycles preview their anchor. */

export const DAY_CYCLE_PREFIX = "cycle:";

export const DAY_CYCLE_PRESETS: Array<{ label: string; base: number; home: number }> = [
  { label: "11/3", base: 11, home: 3 },
  { label: "12/2", base: 12, home: 2 },
  { label: "10/4", base: 10, home: 4 },
  { label: "שבוע־שבוע", base: 7, home: 7 },
  { label: "14/7", base: 14, home: 7 },
  { label: "21/7", base: 21, home: 7 },
  { label: "5/2", base: 5, home: 2 },
  { label: "4/3", base: 4, home: 3 },
];

export const GROUP_LETTERS = ["א", "ב", "ג", "ד", "ה", "ו"];

export function isDayCycle(pattern: unknown): pattern is string {
  return typeof pattern === "string" && pattern.startsWith(DAY_CYCLE_PREFIX);
}

export function cyclePattern(cycle: Pick<DayCycle, "id">): string {
  return `${DAY_CYCLE_PREFIX}${cycle.id}`;
}

export function cycleOf(cycles: DayCycle[] | undefined, pattern: unknown): DayCycle | undefined {
  if (!isDayCycle(pattern)) return undefined;
  const id = pattern.slice(DAY_CYCLE_PREFIX.length);
  return (cycles ?? []).find((cycle) => cycle.id === id);
}

export function cycleName(cycles: DayCycle[] | undefined, pattern: unknown): string {
  return cycleOf(cycles, pattern)?.name || "מחזור";
}

export function newDayCycle(existing: DayCycle[]): DayCycle {
  const used = new Set(existing.map((cycle) => cycle.id));
  let index = existing.length + 1;
  while (used.has(`c${index}`)) index += 1;
  return {
    id: `c${index}`, name: "11/3", base_days: 11, home_days: 3, anchor_date: "",
    groups: ["א", "ב"], offsets: {}, leave_day: 0, leave_time: "", return_day: 0,
    return_time: "", group_times: {}, time_changes: [],
  };
}

/** Matches `day_cycles.default_offset`: groups spread evenly over the cycle. */
export function defaultOffset(cycle: DayCycle, group: string): number {
  const length = cycle.base_days + cycle.home_days;
  const index = cycle.groups.indexOf(group);
  if (index < 0 || !length) return 0;
  return Math.round((index * length) / cycle.groups.length) % length;
}

export function groupOffset(cycle: DayCycle, group: string): number {
  const stated = cycle.offsets?.[group];
  return typeof stated === "number" ? stated : defaultOffset(cycle, group);
}

/** Setup preview only: whether `group` is nominally home on day `n` after
 *  the anchor. Hours and dated changes are applied by the server. */
export function nominallyHome(cycle: DayCycle, group: string, n: number): boolean {
  const length = cycle.base_days + cycle.home_days;
  if (!length) return false;
  const position = (((n - groupOffset(cycle, group)) % length) + length) % length;
  return position >= cycle.base_days;
}
