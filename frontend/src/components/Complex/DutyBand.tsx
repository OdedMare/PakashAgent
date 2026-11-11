"use client";

import { AlertTriangle, Soup } from "lucide-react";

import { isWeekend } from "@/components/Management/Calendar";
import { colorStyle } from "@/components/Management/palette";
import type { ComplexDuty, DutyBoard, DutyType } from "@/types";

import type { Focus } from "./figures";
import { runsOn } from "./useDuties";

/** The מכלול's duties on the combined board, as one more band: a row per
 *  kind of duty, a column per day, each soldier a card in the colour they
 *  wear on their own משמרת's rows. Like the rest of that board it reads and
 *  never writes — "ניהול התורנויות" opens the duties tab, where a seat is
 *  set.
 *
 *  The board's filters hide here as they do above: a משמרת or a soldier
 *  narrows the cards, a shift type leaves no duty to show, and "רק חוסרים"
 *  keeps the kinds with an open seat. */
export function DutyBand({
  board, days, today, focus, dark, hueOf, onManage,
}: {
  board: DutyBoard;
  days: string[];
  today: string;
  focus: Focus;
  dark: boolean;
  hueOf: (name: string) => number;
  onManage: () => void;
}) {
  const rows = dutyRows(board, days, focus);
  if (rows.length === 0) return null;
  const visible = (duty: ComplexDuty) =>
    (!focus.unit || duty.team_id === focus.unit)
    && (!focus.soldier || focus.soldier === `${duty.team_id}:${duty.employee}`);
  let open = 0;
  for (const type of rows) {
    for (const day of days) open += openSeats(type, day, dutiesOn(board, type, day));
  }

  return (
    <>
      <div className="cmd-band cmd-duty-band" role="rowgroup">
        <span className="cmd-band-name">תורנויות</span>
        {open ? (
          <span className="cmd-band-warn"><AlertTriangle size={12} /> {open} מקומות פנויים</span>
        ) : null}
        <button type="button" className="ghost-button cmd-band-enter" onClick={onManage}>
          <Soup size={14} /> ניהול התורנויות
        </button>
      </div>
      {rows.map((type) => (
        <div key={type.id} className="cmd-row" role="row">
          <div className="board-rowhead" role="rowheader">
            <span className="cmd-shift-name board-rowhead-name">{type.name}</span>
            <span className="board-rowhead-hours">
              {type.seats} ביום{!type.active ? " · הושבתה" : ""}
            </span>
          </div>
          {days.map((day) => {
            const on = dutiesOn(board, type, day);
            const missing = openSeats(type, day, on);
            const base = ["board-cell", isWeekend(day) ? "is-weekend" : "", day === today ? "is-today" : ""];
            if (on.length === 0 && !(type.active && runsOn(type, day))) {
              return (
                <div key={day} role="cell" className={[...base, "is-absent"].join(" ")}>
                  <span className="visually-hidden">התורנות לא פעילה ביום הזה</span>
                </div>
              );
            }
            return (
              <div key={day} role="cell" className={[...base, missing ? "is-short" : ""].filter(Boolean).join(" ")}>
                {on.filter(visible).map((duty) => (
                  <div key={duty.id}
                    className={`board-card cmd-card${duty.blocks ? " is-published" : " duty-card is-record"}`}
                    style={colorStyle(hueOf(`${duty.team_id}:${duty.employee}`), dark)}
                    title={[duty.note, duty.blocks ? "" : "רישום בלבד: נספר, לא חוסם"].filter(Boolean).join(" · ") || undefined}>
                    <div className="board-card-main">
                      <span className="board-card-name">{duty.employee}</span>
                      <span className="board-card-role">{duty.team_name}{duty.blocks ? "" : " · רישום"}</span>
                    </div>
                  </div>
                ))}
                {missing ? (
                  <span className="board-gap">
                    <AlertTriangle size={11} /> {missing > 1 ? `${missing} פנויים` : "פנוי"}
                  </span>
                ) : null}
              </div>
            );
          })}
        </div>
      ))}
    </>
  );
}

function dutiesOn(board: DutyBoard, type: DutyType, day: string): ComplexDuty[] {
  return board.duties.filter((duty) => duty.duty_type_id === type.id && duty.duty_date === day);
}

function openSeats(type: DutyType, day: string, on: ComplexDuty[]): number {
  if (!type.active || !runsOn(type, day)) return 0;
  return Math.max(0, type.seats - on.filter((duty) => duty.blocks).length);
}

/** The kinds of duty the board's filters leave in: active ones, and a
 *  switched-off one that still has somebody on it in the range. */
export function dutyRows(board: DutyBoard | null, days: string[], focus: Focus): DutyType[] {
  if (!board || focus.shift) return [];
  return board.types.filter((type) => {
    const mine = board.duties.filter((duty) => duty.duty_type_id === type.id && days.includes(duty.duty_date));
    if (!type.active && mine.length === 0) return false;
    if (focus.soldier && !mine.some((duty) => focus.soldier === `${duty.team_id}:${duty.employee}`)) return false;
    if (focus.gapsOnly && !days.some((day) => openSeats(type, day, dutiesOn(board, type, day)) > 0)) return false;
    return true;
  });
}
