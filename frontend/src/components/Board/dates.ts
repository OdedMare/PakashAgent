/** Date arithmetic for the board, on `YYYY-MM-DD` strings.
 *
 *  Strings in and strings out because that is what the API speaks and what
 *  the grid keys on; a `Date` is built only for the step in between. Every
 *  one of them is built at local midnight (`T00:00:00`), never parsed bare —
 *  a bare ISO date is read as UTC, which in Israel is the previous evening.
 */

/** Today, in the browser's own timezone, as `YYYY-MM-DD`.
 *
 *  Built from the local date parts rather than `toISOString()`, which
 *  converts to UTC first: at 01:00 in Israel that returns *yesterday*, which
 *  would open the board on the previous week for two hours every night. */
export function localToday(): string {
  return isoOf(new Date());
}

/** Whether a string is a date this file can do arithmetic on. */
export function isDay(iso: string): boolean {
  return !Number.isNaN(new Date(`${iso}T00:00:00`).getTime());
}

/** The Sunday on or before this date.
 *
 *  Sunday-based to match `week_bounds()` in the repository, which is itself
 *  Sunday-based because the real source files run ראשון through שבת. The two
 *  must agree: a board built on a Monday week would ask the server for a
 *  period whose bounds never line up with what it renders. */
export function sundayOf(iso: string): string {
  const date = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(date.getTime())) return iso;
  date.setDate(date.getDate() - date.getDay());
  return isoOf(date);
}

export function addDays(iso: string, days: number): string {
  const date = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(date.getTime())) return iso;
  date.setDate(date.getDate() + days);
  return isoOf(date);
}

/** The same day of the month, `months` away.
 *
 *  Clamped to the target month's last day: a month after the 31st of January
 *  is the end of February, not the 3rd of March, which is where `setMonth`
 *  alone lands and would skip a month every time the manager paged from a
 *  long one into a short one. */
export function addMonths(iso: string, months: number): string {
  const date = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(date.getTime())) return iso;
  const target = new Date(date.getFullYear(), date.getMonth() + months, 1);
  const last = new Date(
    target.getFullYear(),
    target.getMonth() + 1,
    0,
  ).getDate();
  target.setDate(Math.min(date.getDate(), last));
  return isoOf(target);
}

/** The first and last day of the month this date falls in. */
export function monthBounds(iso: string): { first: string; last: string } {
  const date = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(date.getTime())) return { first: iso, last: iso };
  return {
    first: isoOf(new Date(date.getFullYear(), date.getMonth(), 1)),
    last: isoOf(new Date(date.getFullYear(), date.getMonth() + 1, 0)),
  };
}

/** The seven dates of the week starting here, in order. */
export function weekDates(start: string): string[] {
  return Array.from({ length: 7 }, (_, index) => addDays(start, index));
}

/** Every date from `start` to `end`, both included. */
export function datesBetween(start: string, end: string): string[] {
  if (!isDay(start) || !isDay(end)) return [];
  const dates: string[] = [];
  for (let day = start; day <= end; day = addDays(day, 1)) dates.push(day);
  return dates;
}

function isoOf(date: Date): string {
  const month = `${date.getMonth() + 1}`.padStart(2, "0");
  const day = `${date.getDate()}`.padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
}
