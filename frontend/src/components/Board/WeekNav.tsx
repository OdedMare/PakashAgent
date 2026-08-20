"use client";

import { CalendarCheck, ChevronLeft, ChevronRight } from "lucide-react";

import { hebrewWeekday } from "@/components/Management/Calendar";

/** Moving between weeks.
 *
 *  The arrows are mirrored for RTL and that is not decoration: in a
 *  right-to-left board the *previous* week sits to the right, so an arrow
 *  pointing right must go back. Pointing them the LTR way would send the
 *  manager the wrong direction every time, which is the single most common
 *  way an RTL interface is got wrong.
 *
 *  "היום" is always present rather than appearing only when the manager has
 *  paged away. A control that comes and goes has to be looked for; one that
 *  is always in the same place is pressed without thinking, and it is
 *  disabled rather than hidden when the current week is already showing so
 *  its position stays constant.
 */
export function WeekNav({
  weekStart,
  weekEnd,
  isCurrentWeek,
  busy,
  onPrevious,
  onNext,
  onToday,
}: {
  weekStart: string;
  weekEnd: string;
  isCurrentWeek: boolean;
  busy?: boolean;
  onPrevious: () => void;
  onNext: () => void;
  onToday: () => void;
}) {
  return (
    <div className="board-weeknav">
      <button
        type="button"
        className="board-nav-button"
        onClick={onPrevious}
        aria-label="שבוע קודם"
        title="שבוע קודם"
      >
        <ChevronRight size={18} />
      </button>

      <div className="board-week-label">
        <span className="board-week-range">{formatRange(weekStart, weekEnd)}</span>
        <span className="board-week-sub">
          {isCurrentWeek ? "השבוע הנוכחי" : `${hebrewWeekday(weekStart)}–${hebrewWeekday(weekEnd)}`}
        </span>
      </div>

      <button
        type="button"
        className="board-nav-button"
        onClick={onNext}
        aria-label="שבוע הבא"
        title="שבוע הבא"
      >
        <ChevronLeft size={18} />
      </button>

      <button
        type="button"
        className="board-today-button"
        onClick={onToday}
        disabled={isCurrentWeek || busy}
        title="חזרה לשבוע הנוכחי"
      >
        <CalendarCheck size={15} />
        היום
      </button>
    </div>
  );
}

/** A week as one readable Hebrew range.
 *
 *  The month is written once when both ends share it — "16–22 באוגוסט"
 *  rather than "16 באוגוסט – 22 באוגוסט", which is how the range is
 *  actually said. `Intl` supplies the month name so it is the browser's
 *  Hebrew rather than a table this file would have to maintain. */
function formatRange(start: string, end: string): string {
  const from = new Date(`${start}T00:00:00`);
  const to = new Date(`${end}T00:00:00`);
  if (Number.isNaN(from.getTime()) || Number.isNaN(to.getTime())) {
    return `${start} – ${end}`;
  }
  const month = new Intl.DateTimeFormat("he-IL", { month: "long" });
  const sameMonth = from.getMonth() === to.getMonth();
  if (sameMonth) {
    return `${from.getDate()}–${to.getDate()} ב${month.format(to)}`;
  }
  return `${from.getDate()} ב${month.format(from)} – ${to.getDate()} ב${month.format(to)}`;
}
