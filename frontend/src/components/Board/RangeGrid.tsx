"use client";

import { AlertTriangle, Repeat2, Sparkles } from "lucide-react";
import { useMemo } from "react";

import { displayDate, shortDate } from "@/components/DateInput";
import { hebrewWeekday, isWeekend } from "@/components/Management/Calendar";
import { buildPalette, colorStyle } from "@/components/Management/palette";
import type { Assignment, CardPerson, Closure, Schedule } from "@/types";

import type { AgentTouch } from "./agentTouch";
import { datesBetween, weekDates } from "./dates";
import { buildScheduleIndex } from "./scheduleIndex";
import { useShiftOrder } from "./shiftOrder";
import { periodOn } from "./span";
import type { BoardFilters } from "./useBoard";

/** Two weeks, or a month, as a calendar: weeks down, days across.
 *
 *  The week board answers "who is on Tuesday". This answers the questions a
 *  week is too narrow for — is the month built, which days are short, how do
 *  somebody's shifts fall across it — and it does so with the same facts the
 *  board uses: the same index, the same seat count, the same row order, the
 *  same colour per person. It is the board from further away, not a second
 *  opinion about it.
 *
 *  **Nothing here writes, and that is the design rather than a gap.** A span
 *  crosses periods, and every write the board makes names the one period it
 *  lands on. So a day is a button that opens that day, and a week's label
 *  opens that week — which is where placing, dragging and the reason a drag
 *  owes ([D12](../../../docs/DECISIONS.md#d12--dragging-a-shift-is-a-proposal-not-an-edit))
 *  already live. A drag across this grid would be a move between two
 *  periods with no dialog able to say which audit it answers to.
 *
 *  **A day with no period says so.** "לא תוכנן" and an empty day inside a
 *  built week are different facts, and only the first is an invitation to
 *  build something.
 */
export function RangeGrid({
  start,
  end,
  month,
  today,
  span,
  periods,
  employees,
  roles,
  people,
  filters,
  dark,
  busy = false,
  touches,
  onOpenDay,
  onOpenWeek,
}: {
  start: string;
  end: string;
  /** `YYYY-MM` of the month being shown, when it is a month. Days outside
   *  it are drawn quieter: they are there to finish the week, not as part
   *  of what was asked for. */
  month?: string;
  today: string;
  /** The periods as one clipped span — what the index is built from. */
  span: Schedule | null;
  /** The periods themselves, for which of them a date belongs to. */
  periods: Schedule[];
  employees: string[];
  roles: Record<string, string>;
  people: Record<string, CardPerson>;
  filters: BoardFilters;
  dark: boolean;
  /** The span is still being read. The dates are drawn at once — they come
   *  from `start` and `end` alone — but nothing is claimed about them. */
  busy?: boolean;
  touches?: Map<string, AgentTouch[]>;
  onOpenDay: (date: string) => void;
  onOpenWeek: (date: string) => void;
}) {
  const weeks = useMemo(() => {
    const dates = datesBetween(start, end);
    const rows: string[][] = [];
    for (let at = 0; at < dates.length; at += 7) {
      rows.push(dates.slice(at, at + 7));
    }
    return rows;
  }, [start, end]);

  const index = useMemo(() => buildScheduleIndex(span, people), [span, people]);
  const hueOf = useMemo(() => buildPalette(employees), [employees]);

  const startTimes = useMemo(() => {
    const map: Record<string, string> = {};
    for (const slot of span?.slots ?? []) {
      if (slot.start_time && !map[slot.shift_name]) {
        map[slot.shift_name] = slot.start_time;
      }
    }
    return map;
  }, [span?.slots]);
  // The manager's own row order, the one the week board reads in. A month
  // that listed the shifts differently from the week it opens into would
  // have to be re-read on every click.
  const order = useShiftOrder({ shifts: index.shifts, startTimes });

  const flagged = useMemo(() => {
    const map = new Map<string, number>();
    for (const row of span?.warnings ?? []) {
      if (row.severity !== "warning") continue;
      map.set(row.date, (map.get(row.date) ?? 0) + 1);
    }
    return map;
  }, [span?.warnings]);

  const closures = useMemo(() => {
    const map = new Map<string, Closure>();
    for (const row of span?.closures ?? []) {
      if (row.groups.length) map.set(row.date, row);
    }
    return map;
  }, [span?.closures]);

  // Which dates the agent is pointing at. The board marks the cell; from
  // this far out the day is the smallest thing there is to mark.
  const touched = useMemo(() => {
    const dates = new Set<string>();
    for (const key of touches?.keys() ?? []) {
      dates.add(key.slice(key.lastIndexOf("|") + 1));
    }
    return dates;
  }, [touches]);

  const narrowed = Boolean(filters.employee || filters.role);
  const shown = (row: Assignment) =>
    (!filters.employee || row.employee === filters.employee) &&
    (!filters.role || (roles[row.employee] ?? "") === filters.role);
  // A month has a third of the room per day that a fortnight has, so it
  // names the first few people on a shift and counts the rest.
  const nameLimit = month ? 3 : Number.POSITIVE_INFINITY;

  return (
    <div className="board-grid-scroll" data-tour="grid">
      <div
        className={`range-grid${month ? " is-month" : ""}`}
        dir="rtl"
        aria-busy={busy || undefined}
      >
        <div className="range-corner" aria-hidden="true">
          שבוע
        </div>
        {weekDates(start).map((date) => (
          <div
            key={date}
            className={`range-weekday${isWeekend(date) ? " is-weekend" : ""}`}
          >
            {hebrewWeekday(date)}
          </div>
        ))}

        {weeks.map((dates) => {
          const statuses = Array.from(
            new Set(
              dates
                .map((date) => periodOn(periods, date)?.status)
                .filter((status): status is Schedule["status"] =>
                  Boolean(status),
                ),
            ),
          );
          const first = dates[0];
          const last = dates[dates.length - 1];

          return (
            <div key={first} className="range-week" role="presentation">
              <button
                type="button"
                className="range-weekhead"
                onClick={() => onOpenWeek(first)}
                aria-label={`פתיחת השבוע ${displayDate(first)} עד ${displayDate(last)}`}
                title="פתיחת השבוע בלוח"
              >
                <span className="range-weekhead-dates">
                  {shortDate(first)}–{shortDate(last)}
                </span>
                {busy ? null : statuses.length ? (
                  statuses.map((status) => (
                    <span
                      key={status}
                      className={`range-weekhead-status is-${status}`}
                    >
                      {status === "published" ? "פורסם" : "טיוטה"}
                    </span>
                  ))
                ) : (
                  <span className="range-weekhead-status is-none">
                    אין סידור
                  </span>
                )}
              </button>

              {dates.map((date) => {
                const planned = Boolean(periodOn(periods, date));
                const { assigned, required } = index.dayCoverage(date);
                const missing = Math.max(0, required - assigned);
                const warnings = flagged.get(date) ?? 0;
                const closure = closures.get(date);
                const hidden =
                  !busy &&
                  ((filters.unassignedOnly && !missing) ||
                    (filters.conflictsOnly && !warnings));

                const rows = busy || hidden
                  ? []
                  : order.shifts
                      .filter(
                        (shift) => !filters.shift || shift === filters.shift,
                      )
                      .map((shift) => {
                        const slot = index.slot(shift, date);
                        if (!slot) return null;
                        const names = index.assignments(shift, date).filter(shown);
                        // Seats, never cards — the same count the board's
                        // own "חסרים" badge is measured in.
                        const short = Math.max(
                          0,
                          slot.headcount - index.filledSeats(shift, date),
                        );
                        return { shift, names, short };
                      })
                      .filter(
                        (
                          row,
                        ): row is {
                          shift: string;
                          names: Assignment[];
                          short: number;
                        } => {
                          if (!row) return false;
                          // Narrowed to a person or a role, a shift they are
                          // not on is not part of the answer.
                          if (narrowed && !row.names.length) return false;
                          if (filters.unassignedOnly && !row.short) return false;
                          return true;
                        },
                      );

                const summary = busy
                  ? "נטען"
                  : !planned
                    ? "לא תוכנן"
                    : !required
                      ? "אין משמרות"
                      : `${assigned} מתוך ${required} מקומות מאוישים` +
                        (warnings ? `, ${warnings} התנגשויות` : "");

                return (
                  <button
                    key={date}
                    type="button"
                    className={[
                      "range-day",
                      date === today ? "is-today" : "",
                      isWeekend(date) ? "is-weekend" : "",
                      month && date.slice(0, 7) !== month ? "is-outside" : "",
                      busy ? "is-loading" : "",
                      !busy && !planned ? "is-unplanned" : "",
                      !busy && missing ? "is-short" : "",
                      !busy && warnings ? "has-warning" : "",
                      hidden ? "is-filtered" : "",
                      touched.has(date) ? "is-touched" : "",
                    ]
                      .filter(Boolean)
                      .join(" ")}
                    onClick={() => onOpenDay(date)}
                    aria-label={`${hebrewWeekday(date)} ${displayDate(date)}: ${summary}. פתיחת היום`}
                    title="פתיחת היום"
                  >
                    <span className="range-day-head">
                      <span className="range-day-number">
                        {dayNumber(date, date === start)}
                      </span>
                      {date === today ? (
                        <span className="range-day-pill">היום</span>
                      ) : null}
                      {touched.has(date) ? (
                        <span className="range-day-touch" aria-hidden="true">
                          <Sparkles size={10} />
                        </span>
                      ) : null}
                      {!busy && warnings ? (
                        <span className="range-day-flag">
                          <AlertTriangle size={10} aria-hidden="true" />
                          {warnings}
                        </span>
                      ) : null}
                      {!busy && required ? (
                        <span
                          className={`range-day-coverage${missing ? " is-short" : ""}`}
                        >
                          {assigned}/{required}
                        </span>
                      ) : null}
                    </span>

                    {!busy && closure ? (
                      <span
                        className={`range-day-closure${closure.until_handover ? " is-handover" : ""}`}
                      >
                        <Repeat2 size={10} aria-hidden="true" />
                        {closure.until_handover
                          ? `${closure.label} · חילוף`
                          : closure.label}
                      </span>
                    ) : null}

                    {!busy && !planned ? (
                      <span className="range-day-none">לא תוכנן</span>
                    ) : null}

                    {rows.map((row) => (
                      <span key={row.shift} className="range-shift">
                        <span className="range-shift-name">{row.shift}</span>
                        <span className="range-shift-people">
                          {row.names.slice(0, nameLimit).map((person) => (
                            <span
                              key={person.id}
                              className="range-person"
                              style={colorStyle(hueOf(person.employee), dark)}
                            >
                              {person.employee}
                            </span>
                          ))}
                          {row.names.length > nameLimit ? (
                            <span className="range-more">
                              +{row.names.length - nameLimit}
                            </span>
                          ) : null}
                          {/* Not while narrowed to a person: the seats a
                              shift is short of are not theirs to be short
                              of, and the figure would read as a fact about
                              them. */}
                          {row.short && !narrowed ? (
                            <span className="range-short">
                              חסרים {row.short}
                            </span>
                          ) : null}
                        </span>
                      </span>
                    ))}
                  </button>
                );
              })}
            </div>
          );
        })}
      </div>
    </div>
  );
}

/** The date as the cell's heading.
 *
 *  A bare number, except where the month would otherwise be a guess: the
 *  first cell of the grid and every 1st carry it, so a span that crosses a
 *  month boundary never shows a "1" following a "31" with nothing between
 *  them. */
function dayNumber(iso: string, isFirst: boolean): string {
  const date = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(date.getTime())) return iso;
  if (date.getDate() !== 1 && !isFirst) return `${date.getDate()}`;
  const month = new Intl.DateTimeFormat("he-IL", { month: "short" });
  return `${date.getDate()} ב${month.format(date)}`;
}
