/**
 * Weekday names as the setup form stores them.
 *
 * A profile can hold either "שני" or "יום שני" for the same day: the
 * interview collects both, and the backend treats them as one
 * (`_weekday_key` in `bl/scheduler.py` and `bl/audit.py`). The checkboxes
 * compare exact strings, so the form reads every day list through
 * `weekdayNames`. Otherwise a prefixed day shows unticked, and ticking it
 * saves both spellings of the same day.
 */
export const WEEKDAYS = ["ראשון", "שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת"];

const PREFIX = "יום ";

/** One day name without the optional "יום " prefix. */
export function weekdayName(value: string): string {
  const day = value.trim();
  return day.startsWith(PREFIX) ? day.slice(PREFIX.length).trim() : day;
}

/**
 * A stored day list in the form's spelling: unprefixed, each day once, in
 * week order. A value that is not a weekday is kept after the weekdays
 * rather than dropped, so saving never loses data the form cannot show.
 */
export function weekdayNames(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  const names = new Set<string>();
  for (const item of value) {
    if (typeof item !== "string") continue;
    const day = weekdayName(item);
    if (day) names.add(day);
  }
  const known = WEEKDAYS.filter((day) => names.has(day));
  const other = [...names].filter((day) => !WEEKDAYS.includes(day));
  return [...known, ...other];
}
