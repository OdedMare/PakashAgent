/** Small Hebrew formatters the console shares. Pure, no state. */

const DATE = new Intl.DateTimeFormat("he-IL", { day: "numeric", month: "short", year: "numeric" });
const SHORT = new Intl.DateTimeFormat("he-IL", { day: "numeric", month: "numeric" });
const RELATIVE = new Intl.RelativeTimeFormat("he", { numeric: "auto" });

export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : DATE.format(date);
}

export function formatShort(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : SHORT.format(date);
}

/** "לפני 3 ימים" — the scale a glance at a team list needs. */
export function formatRelative(value: string | null | undefined): string {
  if (!value) return "—";
  const then = new Date(value).getTime();
  if (Number.isNaN(then)) return "—";
  const minutes = Math.round((then - Date.now()) / 60000);
  if (Math.abs(minutes) < 1) return "עכשיו";
  if (Math.abs(minutes) < 60) return relative(minutes, "minute");
  const hours = Math.round(minutes / 60);
  if (Math.abs(hours) < 24) return relative(hours, "hour");
  const days = Math.round(hours / 24);
  if (Math.abs(days) < 45) return relative(days, "day");
  return formatDate(value);
}

/** ICU's Hebrew data writes the singular as "לפני דקה (1)"; the bracketed
 *  count repeats what the word already says. */
function relative(value: number, unit: Intl.RelativeTimeFormatUnit): string {
  return RELATIVE.format(value, unit).replace(/\s*\(\d+\)$/, "");
}

export function formatBytes(bytes: number | undefined): string {
  if (!bytes) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(value < 10 && unit > 0 ? 1 : 0)} ${units[unit]}`;
}

/** A manager password the operator can read aloud: no 0/O or 1/l. */
export function generatePassword(): string {
  const alphabet = "abcdefghjkmnpqrstuvwxyz23456789";
  const bytes = new Uint32Array(10);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (value) => alphabet[value % alphabet.length]).join("");
}
