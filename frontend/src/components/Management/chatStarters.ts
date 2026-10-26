import type { ConstraintRequestRow, ScheduleWarning } from "@/types";
import { displayDate as formatDate } from "@/components/DateInput";
import { hebrewWeekday } from "./Calendar";

const WEEK_STARTERS = ["מי יכול להחליף ברביעי?", "מי משובץ הכי הרבה בסופ״ש?", "תשבץ את שני כמו בשבוע שעבר", "אני רוצה להוסיף אילוץ קבוע לעובד"];
const DAY_STARTERS = ["תשבץ את היום הזה", "תמלא רק את המשמרות הפנויות ביום הזה", "מי זמין להחליף ביום הזה?", "איך כדאי לפתור חוסר בעובדים ביום הזה?"];
const MAX_STARTERS = 4;

/** Openers built from what is actually on the board: empty shifts and
 *  requests waiting for an answer come first, then the general ones. Each is
 *  sent as the manager's own message, so it states the date and person in
 *  full rather than pointing at something the agent cannot see. */
export function chatStarters({ warnings, requests, focusDate }: {
  warnings: ScheduleWarning[]; requests: ConstraintRequestRow[]; focusDate: string;
}): string[] {
  const unfilled = warnings.filter((row) => row.code === "unfilled" && row.date && (!focusDate || row.date === focusDate));
  const found: string[] = [];
  const days = [...new Set(unfilled.map((row) => row.date))].sort();
  if (focusDate && days.length) found.push(`יש משמרות פנויות ביום ${hebrewWeekday(focusDate)} ${formatDate(focusDate)} — תמלא אותן`);
  else if (days.length === 1) found.push(`תמלא את המשמרות הפנויות ביום ${hebrewWeekday(days[0])} ${formatDate(days[0])}`);
  else if (days.length > 1) found.push(`יש ${unfilled.length} משמרות פנויות השבוע — איך כדאי למלא אותן?`);
  const pending = requests.filter((row) => row.status === "pending");
  if (pending.length === 1) found.push(`מה דעתך על הבקשה של ${pending[0].employee} ל־${formatDate(pending[0].constraint_date)}?`);
  else if (pending.length > 1) found.push(`יש ${pending.length} בקשות אילוץ שממתינות — תעבור עליהן איתי`);
  for (const value of focusDate ? DAY_STARTERS : WEEK_STARTERS) if (!found.includes(value)) found.push(value);
  return found.slice(0, MAX_STARTERS);
}
