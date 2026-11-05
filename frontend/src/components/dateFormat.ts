/** Date display formats, kept apart from `DateInput` so hooks and pure
 * modules can format a date without importing a component (and its icons). */

/** `DD/MM/YYYY`, the Israeli order, from an ISO `YYYY-MM-DD`. */
export function displayDate(iso: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  return match ? `${match[3]}/${match[2]}/${match[1]}` : iso;
}

/** `DD/MM`, for places where the year is already obvious from context. */
export function shortDate(iso: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  return match ? `${match[3]}/${match[2]}` : iso;
}
