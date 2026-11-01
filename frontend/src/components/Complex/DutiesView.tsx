"use client";

import { AlertTriangle, History, Plus, Settings2, X } from "lucide-react";
import { useState } from "react";

import { displayDate } from "@/components/DateInput";
import { hebrewWeekday } from "@/components/Management/Calendar";
import type { ComplexDuty, DutyType } from "@/types";

import { DutyForm } from "./DutyForm";
import { DutyTypes } from "./DutyTypes";
import { runsOn, useDuties } from "./useDuties";

type Panel =
  | { kind: "assign"; typeId: string; date: string }
  | { kind: "record" }
  | { kind: "types" }
  | null;

/** The מכלול's duties over the range on screen: one row per kind of duty,
 *  one column per day, the soldiers standing it in each cell.
 *
 *  A seat is set here, by hand, from every משמרת's soldiers; the day is then
 *  blocked in that soldier's own משמרת and its commander is told. A duty
 *  already stood is recorded from "רישום תורנות שכבר נעשתה" -- it counts in
 *  fairness and statistics and blocks nothing. */
export function DutiesView({ days, today }: { days: string[]; today: string }) {
  const start = days[0] ?? today;
  const end = days[days.length - 1] ?? today;
  const duties = useDuties(start, end);
  const [panel, setPanel] = useState<Panel>(null);
  const board = duties.board;
  const types = board?.types ?? [];
  const shown = types.filter((type) => type.active
    || board?.duties.some((duty) => duty.duty_type_id === type.id));

  const on = (type: DutyType, date: string): ComplexDuty[] =>
    (board?.duties ?? []).filter((duty) => duty.duty_type_id === type.id && duty.duty_date === date);

  return (
    <div className="duties">
      <div className="duty-toolbar" role="group" aria-label="פעולות התורנויות">
        <button type="button" className="ghost-button" onClick={() => setPanel({ kind: "types" })}>
          <Settings2 size={15} /> סוגי תורנויות
        </button>
        <button type="button" className="ghost-button" disabled={!types.length}
          onClick={() => setPanel({ kind: "record" })}>
          <History size={15} /> רישום תורנות שכבר נעשתה
        </button>
      </div>

      {duties.error ? (
        <div className="error" role="alert">
          <AlertTriangle size={16} /><span>{duties.error}</span>
          <button type="button" className="icon-button subtle" onClick={duties.clearError} aria-label="סגירה">
            <X size={14} />
          </button>
        </div>
      ) : null}

      {panel?.kind === "types" ? (
        <div className="duty-panel">
          <button type="button" className="icon-button subtle duty-panel-close"
            onClick={() => setPanel(null)} aria-label="סגירה"><X size={15} /></button>
          <DutyTypes types={types} busy={duties.busy} onCreate={duties.createType}
            onUpdate={duties.updateType} onDelete={duties.deleteType} />
        </div>
      ) : panel ? (
        <DutyForm
          key={panel.kind === "assign" ? `${panel.typeId}-${panel.date}` : "record"}
          record={panel.kind === "record"}
          types={types}
          roster={duties.roster}
          duties={board?.duties ?? []}
          initialType={panel.kind === "assign" ? panel.typeId : ""}
          initialDate={panel.kind === "assign" ? panel.date : today}
          busy={duties.busy}
          onSubmit={duties.assign}
          onClose={() => setPanel(null)}
        />
      ) : null}

      {board === null ? null : shown.length === 0 ? (
        <p className="cmd-empty">
          עדיין אין תורנויות במכלול. פתחו את &quot;סוגי תורנויות&quot; והוסיפו את הראשונה.
        </p>
      ) : (
        <div className="duty-grid-wrap">
          <table className="duty-grid">
            <thead>
              <tr>
                <th scope="col">תורנות</th>
                {days.map((date) => (
                  <th scope="col" key={date} className={date === today ? "is-today" : ""}>
                    <span>{hebrewWeekday(date)}</span>
                    <small>{displayDate(date)}</small>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {shown.map((type) => (
                <tr key={type.id}>
                  <th scope="row">
                    <span>{type.name}</span>
                    <small>{type.seats} ביום{type.weight !== 1 ? ` · שווה ${type.weight}` : ""}</small>
                  </th>
                  {days.map((date) => (
                    <DutyCell key={date} type={type} date={date} rows={on(type, date)}
                      busy={duties.busy}
                      onAdd={() => setPanel({ kind: "assign", typeId: type.id, date })}
                      onCancel={(duty) => {
                        if (window.confirm(`לבטל את התורנות של ${duty.employee} ב־${displayDate(duty.duty_date)}?`)) {
                          void duties.cancel(duty.id);
                        }
                      }} />
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function DutyCell({
  type, date, rows, busy, onAdd, onCancel,
}: {
  type: DutyType;
  date: string;
  rows: ComplexDuty[];
  busy: boolean;
  onAdd: () => void;
  onCancel: (duty: ComplexDuty) => void;
}) {
  const runs = type.active && runsOn(type, date);
  const seated = rows.filter((row) => row.blocks).length;
  const open = runs ? Math.max(0, type.seats - seated) : 0;

  return (
    <td className={`duty-cell${runs ? "" : " is-off"}${open ? " is-open" : ""}`}>
      {rows.map((row) => (
        <span key={row.id} className={`duty-chip${row.blocks ? "" : " is-record"}`}
          title={[row.team_name, row.note, row.blocks ? "" : "רישום בלבד: נספר, לא חוסם"]
            .filter(Boolean).join(" · ")}>
          <span className="duty-chip-name">{row.employee}</span>
          <small>{row.team_name}{row.blocks ? "" : " · רישום"}</small>
          <button type="button" className="duty-chip-remove" disabled={busy}
            onClick={() => onCancel(row)} aria-label={`ביטול התורנות של ${row.employee}`}>
            <X size={12} />
          </button>
        </span>
      ))}
      {open ? (
        <button type="button" className="duty-add" disabled={busy} onClick={onAdd}
          aria-label={`שיבוץ ל${type.name} ב־${displayDate(date)}`}>
          <Plus size={13} /> {open > 1 ? `${open} פנויים` : "פנוי"}
        </button>
      ) : null}
    </td>
  );
}
