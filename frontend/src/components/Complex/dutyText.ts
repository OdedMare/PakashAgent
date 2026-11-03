import { displayDate } from "@/components/DateInput";
import type { DutyConflict } from "@/types";

/** What became of a shift a new duty collided with, in one line. */
export function conflictLine(row: DutyConflict): string {
  const shift = `${displayDate(row.date)} · ${row.shift_name}${row.start_time ? ` ${row.start_time}–${row.end_time}` : ""}`;
  const who = row.employee ? `${row.employee} · ` : "";
  switch (row.outcome) {
    case "vacated":
      return `${who}${shift}: הוסר/ה מהמשמרת, והמשבצת מושלמת מחדש בטיוטה`;
    case "vacated_only":
      return `${who}${shift}: הוסר/ה מהמשמרת. בנייה אחרת רצה על השבוע, ולכן המשבצת נשארה פתוחה`;
    case "published":
      return `${who}${shift}: שבוע שפורסם — לא שונה. מפקד המשמרת קיבל הודעה למצוא מחליף`;
    case "past":
      return `${who}${shift}: תאריך שעבר — לא שונה`;
    default:
      return `${who}${shift}${row.status === "published" ? " · שבוע שפורסם" : " · טיוטה"}`;
  }
}
