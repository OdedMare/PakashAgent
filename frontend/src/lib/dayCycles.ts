import type { DayCycle } from "@/types";

/** Day-based cycles as the setup screens name them.
 *
 *  The arithmetic of who is home on which date lives in the server
 *  (`bl/rotation/day_cycles.py`); the only date math here names the
 *  transition weekdays on the setup screen. */

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

export const GROUP_LETTERS = ["א", "ב", "ג", "ד", "ה", "ו", "ז", "ח"];

/** A 1 ל־X runs 2 to 8 groups, one Saturday each. */
export const WEEKEND_GROUPS = { min: 2, max: 8 };

export function isWeekends(cycle: Pick<DayCycle, "kind">): boolean {
  return cycle.kind === "weekends";
}

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

/** The preset a cycle's days match, if any — how the exits list names it.
 *  A 1 ל־X is never one, even when its derived days read 7/7. */
export function presetOf(cycle: Pick<DayCycle, "base_days" | "home_days" | "kind">) {
  if (isWeekends(cycle)) return undefined;
  return DAY_CYCLE_PRESETS.find((preset) => preset.base === cycle.base_days && preset.home === cycle.home_days);
}

/** A 1 ל־X with `count` groups, in the shape the server saves it. */
export function weekendDays(count: number): Pick<DayCycle, "groups" | "base_days" | "home_days"> {
  return { groups: GROUP_LETTERS.slice(0, count), base_days: 7, home_days: 7 * (count - 1) };
}

/** A new 1 ל־X; the anchor is the Saturday group א closes. */
export function newWeekendCycle(existing: DayCycle[], count = 6): DayCycle {
  return { ...newDayCycle(existing), kind: "weekends", name: `1 ל־${count}`, ...weekendDays(count) };
}

/** A new cycle with the given days; a preset's label names it. */
export function newDayCycle(existing: DayCycle[], base = 11, home = 3, name = `${base}/${home}`): DayCycle {
  const used = new Set(existing.map((cycle) => cycle.id));
  let index = existing.length + 1;
  while (used.has(`c${index}`)) index += 1;
  return {
    id: `c${index}`, name, base_days: base, home_days: home, anchor_date: "",
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
