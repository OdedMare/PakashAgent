"use client";

import { CalendarCheck, ChevronLeft, ChevronRight } from "lucide-react";

import { displayDate } from "@/components/DateInput";
import { hebrewWeekday } from "@/components/Management/Calendar";

import type { BoardView } from "./views";

/** Moving through the calendar, one view-width at a time.
 *
 *  A step is whatever is on screen — a day, a week, two weeks, a month — so
 *  the arrows mean "the next one of these" in every view and never show a
 *  date twice.
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
 *  disabled rather than hidden when today is already showing so its
 *  position stays constant.
 */
export function WeekNav({
  view,
  focus,
  rangeStart,
  rangeEnd,
  isCurrent,
  busy,
  onPrevious,
  onNext,
  onToday,
}: {
  view: BoardView;
  /** The day the view is anchored on. A month is named after it, since its
   *  drawn range runs into the months either side. */
  focus: string;
  rangeStart: string;
  rangeEnd: string;
  isCurrent: boolean;
  busy?: boolean;
  onPrevious: () => void;
  onNext: () => void;
  onToday: () => void;
}) {
  const words = WORDS[view];

  return (
    <div className="board-weeknav" data-tour="week-nav">
      <button
        type="button"
        className="board-nav-button"
        onClick={onPrevious}
        aria-label={words.previous}
        title={words.previous}
      >
        <ChevronRight size={18} />
      </button>

      {/* Announced when it changes: the arrows and the view switch both
          rewrite this line, and it is the only thing that says where the
          board now is to somebody not looking at the grid. */}
      <div className="board-week-label" aria-live="polite">
        <span className="board-week-range">
          {title(view, focus, rangeStart, rangeEnd)}
        </span>
        <span className="board-week-sub">
          {isCurrent
            ? words.current
            : subtitle(view, focus, rangeStart, rangeEnd)}
        </span>
      </div>

      <button
        type="button"
        className="board-nav-button"
        onClick={onNext}
        aria-label={words.next}
        title={words.next}
      >
        <ChevronLeft size={18} />
      </button>

      <button
        type="button"
        className="board-today-button"
        onClick={onToday}
        disabled={isCurrent || busy}
        title={words.today}
      >
        <CalendarCheck size={15} />
        היום
      </button>
    </div>
  );
}

/** What each view calls its own step. Spelled out per view rather than
 *  assembled from a noun, because Hebrew agrees in gender and number —
 *  "השבועיים הבאים" is not "שבועיים הבא". */
const WORDS: Record<
  BoardView,
  { previous: string; next: string; current: string; today: string }
> = {
  day: {
    previous: "היום הקודם",
    next: "היום הבא",
    current: "היום",
    today: "חזרה להיום",
  },
  week: {
    previous: "שבוע קודם",
    next: "שבוע הבא",
    current: "השבוע הנוכחי",
    today: "חזרה לשבוע הנוכחי",
  },
  fortnight: {
    previous: "השבועיים הקודמים",
    next: "השבועיים הבאים",
    current: "השבועיים הנוכחיים",
    today: "חזרה לשבועיים הנוכחיים",
  },
  month: {
    previous: "חודש קודם",
    next: "חודש הבא",
    current: "החודש הנוכחי",
    today: "חזרה לחודש הנוכחי",
  },
};

/** The span on screen, named the way it is said. */
function title(
  view: BoardView,
  focus: string,
  start: string,
  end: string,
): string {
  const day = new Date(`${focus}T00:00:00`);
  if (Number.isNaN(day.getTime())) return `${start} – ${end}`;
  if (view === "day") {
    const month = new Intl.DateTimeFormat("he-IL", { month: "long" });
    return `יום ${hebrewWeekday(focus)}, ${day.getDate()} ב${month.format(day)}`;
  }
  if (view === "month") {
    return new Intl.DateTimeFormat("he-IL", {
      month: "long",
      year: "numeric",
    }).format(day);
  }
  return formatRange(start, end);
}

/** The second line, when the span is not the current one. */
function subtitle(
  view: BoardView,
  focus: string,
  start: string,
  end: string,
): string {
  if (view === "day") return displayDate(focus);
  // A month's grid runs into its neighbours, so the range is what the
  // title's bare month name leaves unsaid.
  if (view === "month") return formatRange(start, end);
  return `${hebrewWeekday(start)}–${hebrewWeekday(end)}`;
}

/** A range as one readable Hebrew phrase.
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
  const sameMonth =
    from.getMonth() === to.getMonth() &&
    from.getFullYear() === to.getFullYear();
  if (sameMonth) {
    return `${from.getDate()}–${to.getDate()} ב${month.format(to)}`;
  }
  return `${from.getDate()} ב${month.format(from)} – ${to.getDate()} ב${month.format(to)}`;
}
