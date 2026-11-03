import type { Constraint, ScheduleWarning } from "@/types";

/** Why a person's card is flagged, as words short enough to sit on the card.
 *
 *  The audit's own sentence (`warning.message`) is complete but long — it
 *  repeats the name, the shift and the date the card already shows — so on
 *  the card it used to hide behind a hover on a small triangle, and a manager
 *  saw *that* something was wrong with a soldier but not *what*. This reads
 *  the warning's structured `details` into the part the card does not
 *  already say: which rule, and by how much. The full sentence stays in the
 *  hover and the editor.
 *
 *  An unknown code falls back to the audit's sentence, so a new check still
 *  renders without the board knowing about it (codes.py says the same). */
export function warningHeadline(warning: ScheduleWarning): string {
  const details = warning.details ?? {};
  switch (warning.code) {
    case "unavailable":
      return availabilityHeadline(
        details.constraint_type === "duty"
          ? "תורנות חוסמת"
          : details.is_hard === false
            ? "העדפה שלא לשבץ"
            : "אילוץ",
        text(details.start_time),
        text(details.end_time),
        text(details.reason) || reasonFrom(warning.message),
      );
    case "short_rest": {
      const rest = num(details.rest_hours);
      const minimum = num(details.minimum);
      const earlier = text(details.earlier_shift);
      if (rest !== null && rest <= 0) {
        return earlier ? `חופף למשמרת ${earlier}` : "חופף למשמרת אחרת";
      }
      if (rest === null) return "מנוחה קצרה מדי";
      return `רק ${hours(rest)} ש׳ מנוחה${minimum !== null ? ` (נדרש ${hours(minimum)})` : ""}${earlier ? ` אחרי ${earlier}` : ""}`;
    }
    case "over_hours": {
      const total = num(details.hours);
      const limit = num(details.limit);
      if (total === null) return "חריגה בשעות השבועיות";
      return `${hours(total)} ש׳ השבוע${limit !== null ? ` (תקרה ${hours(limit)})` : ""}`;
    }
    case "weekly_shifts": {
      const count = num(details.count);
      const max = num(details.max);
      if (count === null || max === null) return warning.message;
      return details.within_overflow === false
        ? `משמרת ${count} השבוע · מעבר לחריגה המותרת (מקס׳ ${max})`
        : `משמרת ${count} השבוע · חריגה מהמקס׳ (${max})`;
    }
    case "consecutive": {
      const days = num(details.days);
      const limit = num(details.limit);
      if (days === null) return "יותר מדי ימים ברצף";
      return `${days} ימים ברצף${limit !== null ? ` (מקס׳ ${limit})` : ""}`;
    }
    case "below_level": {
      const have = LEVEL_NAMES[text(details.competence)];
      const need = LEVEL_NAMES[text(details.required)];
      if (!have || !need) return "רמה מקצועית נמוכה למשמרת חזקה";
      return `רמה ${have} · המשמרת דורשת ${need}${text(details.required) === "excellent" ? "" : " ומעלה"}`;
    }
    case "double_booked":
      return "משובץ/ת פעמיים באותה משמרת";
    case "cross_rotation": {
      const group = text(details.rotation_group);
      return group ? `בבית לפי הסבב (קבוצה ${group})` : "בבית לפי הסבב";
    }
    default:
      return warning.message;
  }
}

/** רמה מקצועית, as the roster names it. */
const LEVEL_NAMES: Record<string, string> = {
  weak: "חלשה",
  medium: "בינונית",
  high: "גבוהה",
  excellent: "מצטיינת",
};

/** The same line for a recorded constraint the board found on its own —
 *  a hard window the audit has not (yet) reported, e.g. right after a drop. */
export function constraintHeadline(row: Constraint): string {
  return availabilityHeadline(
    row.constraint_type === "duty" ? "תורנות חוסמת" : row.available ? "זמין/ה רק בחלון" : "אילוץ",
    row.start_time,
    row.end_time,
    row.reason,
  );
}

/** The constraint as a full sentence, for the hover. */
export function constraintSentence(employee: string, row: Constraint): string {
  const window = timeWindow(row.start_time, row.end_time);
  const kind =
    row.constraint_type === "duty"
      ? "תורנות שחוסמת את המשמרת"
      : row.available
        ? `זמינות רק ${window || "בחלון אחר"}`
        : "אילוץ למשמרת הזו";
  const parts = [`${employee} — נרשם/ה ${kind}`];
  if (window && !row.available) parts.push(`בשעות ${window}`);
  if (row.reason) parts.push(`סיבה: ${row.reason}`);
  return parts.join(", ") + ".";
}

function availabilityHeadline(kind: string, start: string, end: string, reason: string): string {
  const window = timeWindow(start, end);
  return [kind + (window ? ` ${window}` : ""), reason].filter(Boolean).join(" · ");
}

/** Hours as written, kept left to right inside a Hebrew line: without the
 *  isolate an RTL paragraph lays "12:00–20:00" out as "20:00–12:00". */
function timeWindow(start: string, end: string): string {
  const from = clock(start);
  const to = clock(end);
  if (from && to) return `\u2066${from}–${to}\u2069`;
  if (from) return `מ-${from}`;
  if (to) return `עד ${to}`;
  return "";
}

function clock(value: string): string {
  const match = /^(\d{2}:\d{2})/.exec(value || "");
  return match ? match[1] : "";
}

/** The constraint's reason, for a response from before the audit put it in
 *  `details`: the last parentheses of its sentence. A time window in those
 *  parentheses is not a reason. */
function reasonFrom(message: string): string {
  const match = /\(([^()]*)\)\.?\s*$/.exec(message || "");
  if (!match) return "";
  const inside = match[1].trim();
  return /^(החל מ-|מ-|עד )?\d{2}:\d{2}/.test(inside) ? "" : inside;
}

function text(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function num(value: unknown): number | null {
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function hours(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}
