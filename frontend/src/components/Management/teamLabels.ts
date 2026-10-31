/** Labels and small readers the roster panel and its forms share: the
 *  Hebrew names of sources, service types, exit patterns and shift types,
 *  and the coercions that read loosely typed profile rows. Display only —
 *  nothing here decides anything about a schedule. */

import { cycleName, cycleOf, isDayCycle } from "@/lib/dayCycles";
import type { Constraint, DayCycle } from "@/types";

export function shiftHeadcount(shift?: Record<string, unknown>): number {
  const staffing = Array.isArray(shift?.staffing) ? shift.staffing : [];
  const fallback = staffing.find((group) => {
    if (!group || typeof group !== "object") return false;
    const days = (group as { days?: unknown }).days;
    return !Array.isArray(days) || days.length === 0;
  }) as { headcount?: unknown } | undefined;
  return typeof fallback?.headcount === "number" ? fallback.headcount : 1;
}

/** The weekend's own headcount, when setup gave it one: the staffing group
 *  marked as the closure's, or an older one naming Friday and Saturday. */
export function weekendHeadcount(shift: Record<string, unknown>): number | null {
  const staffing = Array.isArray(shift.staffing) ? shift.staffing as Array<{ days?: unknown; headcount?: unknown; closure?: unknown }> : [];
  const group = staffing.find((row) => row?.closure === true || (Array.isArray(row?.days)
    && row.days.length === 2 && row.days.includes("שישי") && row.days.includes("שבת")));
  return typeof group?.headcount === "number" ? group.headcount : null;
}

export function formatHours(hours: number): string {
  return Number.isInteger(hours) ? `${hours} ש׳` : `${hours.toFixed(1)} ש׳`;
}

/** How each provenance reads to the manager. Deliberately says who supplied
 *  the information, since no employee ever entered it through the app. */
export const SOURCE_LABELS: Record<string, string> = {
  manager: "המנהל",
  agent: "הסוכן",
  employee_reported: "העובד מסר",
  setup: "מהגדרת היחידה",
};

export const SERVICE_TYPE_LABELS: Record<string, string> = {
  standard: "תקן",
  overlap: "נחפף/ת",
  reserve: "מילואים",
};

export const EXIT_PATTERN_LABELS: Record<string, string> = {
  round: "סבב א / ב",
  triplet: "תלתון א / ב / ג",
  quad: "רבעון א / ב / ג / ד",
  quint: "חמישון (1ל5) א–ה",
  hamshushim: "חמשושים",
  shushim: "שושים",
};

export const SHIFT_TYPE_LABELS: Record<string, string> = {
  regular: "רגילה",
  overlap: "חפיפה",
  on_call: "כוננות",
};

export const WEEKDAYS = ["ראשון", "שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת"];

export function formatWindow(row: Constraint): string {
  if (row.start_time && row.end_time) return `${row.start_time}–${row.end_time}`;
  if (row.start_time) return `החל מ־${row.start_time}`;
  if (row.end_time) return `עד ${row.end_time}`;
  return "";
}

export function text(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

export function rawText(value: unknown): string {
  return typeof value === "string" ? value : "";
}

export function patternGroups(pattern: string, cycles: DayCycle[]): string[] {
  if (pattern === "quint") return ["א", "ב", "ג", "ד", "ה"];
  if (pattern === "quad") return ["א", "ב", "ג", "ד"];
  if (pattern === "triplet") return ["א", "ב", "ג"];
  if (pattern === "round") return ["א", "ב"];
  return cycleOf(cycles, pattern)?.groups ?? [];
}

export function exitPatternLabel(person: Record<string, unknown>, cycles: DayCycle[]): string {
  const pattern = text(person.exit_pattern);
  if (isDayCycle(pattern)) return cycleName(cycles, pattern);
  if (EXIT_PATTERN_LABELS[pattern]) return EXIT_PATTERN_LABELS[pattern];
  const group = text(person.rotation_group);
  return group === "ה" ? EXIT_PATTERN_LABELS.quint : group === "ד" ? EXIT_PATTERN_LABELS.quad : group === "ג" ? EXIT_PATTERN_LABELS.triplet : EXIT_PATTERN_LABELS.round;
}

export function strings(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string" && Boolean(item.trim()))
    : [];
}

export function record(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}
