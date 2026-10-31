"use client";

import { CalendarPlus, Eraser, Repeat2, Sparkles } from "lucide-react";

import { hebrewWeekday, isWeekend } from "@/components/Management/Calendar";
import type { Closure } from "@/types";
import { displayDate, shortDate } from "@/components/DateInput";

/** One day's column head.
 *
 *  Today is marked here rather than only on the cells beneath it, because
 *  the head is where the eye lands first when the question is "where am I".
 *  The per-day coverage line under the date is what makes the header worth
 *  its height: it answers "is this day staffed" without reading the column. */
export function DayHead({
  date,
  isToday,
  coverage,
  closure,
  columnRef,
  onOpenAgent,
  onBuildFrom,
  onClear,
  onOpen,
}: {
  date: string;
  isToday: boolean;
  /** Assigned and required for this day, counted once by the index. */
  coverage: { assigned: number; required: number };
  /** Whose closure this day is, when it is one. Undefined on an ordinary
   *  day and on a workplace whose cycle was never anchored — the two are
   *  the same thing here: the rotation has nothing to say. */
  closure?: Closure;
  /** Set on today's head only, so the scroller can bring it into view. */
  columnRef?: React.Ref<HTMLDivElement>;
  onOpenAgent?: () => void;
  onBuildFrom?: () => void;
  onClear?: () => void;
  /** Open this day on its own. The name of the day is the control, as it is
   *  in any calendar: the thing you read is the thing you press. */
  onOpen?: () => void;
}) {
  const { assigned, required } = coverage;
  const name = (
    <>
      <span className="board-dayhead-weekday">{hebrewWeekday(date)}</span>
      <span className="board-dayhead-date">{shortDate(date)}</span>
    </>
  );

  return (
    <div
      ref={columnRef}
      className={[
        "board-dayhead",
        isToday ? "is-today" : "",
        isWeekend(date) ? "is-weekend" : "",
      ]
        .filter(Boolean)
        .join(" ")}
    >
      {onOpen ? (
        <button
          type="button"
          className="board-dayhead-open"
          onClick={onOpen}
          aria-label={`תצוגת יום: ${hebrewWeekday(date)} ${displayDate(date)}`}
          title="פתיחת היום בתצוגת יום"
        >
          {name}
        </button>
      ) : (
        name
      )}
      {required ? (
        <span
          className={`board-dayhead-coverage${
            assigned < required ? " is-short" : ""
          }`}
          title={`${assigned} מתוך ${required} מקומות מאוישים`}
        >
          {assigned}/{required}
        </span>
      ) : (
        <span className="board-dayhead-coverage is-empty">—</span>
      )}
      {isToday ? <span className="board-dayhead-pill">היום</span> : null}
      {/* Whose weekend this is. The single most consequential fact about a
          Thursday, and the one thing the grid underneath cannot show: a
          manager filling a closure day without it is choosing between
          colleagues who are not all in. `until_handover` marks the Sunday a
          closure ends on, where only the morning still belongs to them. */}
      {closure ? (
        <span
          className={`board-dayhead-closure${
            closure.until_handover ? " is-handover" : ""
          }`}
          title={
            (closure.until_handover
              ? `${closure.label} סוגר/ת עד החילוף של הבוקר`
              : `${closure.label} סוגר/ת ביום הזה`) +
            (closure.employees.length
              ? ` — ${closure.employees.join(", ")}`
              : "")
          }
        >
          <Repeat2 size={11} aria-hidden="true" />
          {closure.until_handover ? `${closure.label} · חילוף` : closure.label}
        </span>
      ) : null}
      <div className="board-dayhead-actions">
        {onOpenAgent ? (
          <button
            type="button"
            className="board-dayhead-generate"
            onClick={onOpenAgent}
            aria-label={`הנחיות לסוכן על ${hebrewWeekday(date)} ${displayDate(date)}`}
            title="לפתוח את סוכן הסידור על היום הזה ולתת לו הוראות"
          >
            <Sparkles size={12} />
            סוכן ליום
          </button>
        ) : null}
        {onBuildFrom ? (
          <button
            type="button"
            className="board-dayhead-generate"
            onClick={onBuildFrom}
            aria-label={`בניית הסידור מיום ${hebrewWeekday(date)} ${displayDate(date)} והלאה`}
            title="בניית הסידור מהיום הזה עד שבת, או עד תאריך שתבחרו"
          >
            <CalendarPlus size={12} />
            בנייה מכאן
          </button>
        ) : null}
        {onClear ? (
          <button
            type="button"
            className="board-dayhead-clear"
            onClick={onClear}
            aria-label={`מחיקת המשמרות של ${hebrewWeekday(date)} ${displayDate(date)}`}
            title="מחיקת כל השיבוצים ביום הזה"
          >
            <Eraser size={12} />
            נקה יום
          </button>
        ) : null}
      </div>
    </div>
  );
}
