"use client";

import {
  AlertTriangle, CalendarCheck, Filter, History, Plus, Scale, Settings2, Sparkles, UserMinus, Users, X,
} from "lucide-react";
import { useMemo, useState } from "react";
import type { CSSProperties } from "react";

import { displayDate, shortDate } from "@/components/DateInput";
import { hebrewWeekday, isWeekend } from "@/components/Management/Calendar";
import { buildPalette, colorStyle } from "@/components/Management/palette";
import type { ComplexDuty, ComplexTeam, DutyApproval, DutyProposal, DutySuggestion, DutyType } from "@/types";

import { Tile } from "./parts";

import { DutyBalancePanel } from "./DutyBalancePanel";
import { DutyForm } from "./DutyForm";
import { DutySuggestionBar } from "./DutySuggestionBar";
import { DutyTypes } from "./DutyTypes";
import { runsOn, useDuties } from "./useDuties";

type Panel =
  | { kind: "assign"; typeId: string; date: string }
  | { kind: "record" }
  | { kind: "types" }
  | { kind: "balance" }
  | null;

/** The מכלול's duties over the range on screen, drawn on the board's own
 *  grid: one row per kind of duty, one column per day, each soldier a
 *  `board-card` in the same colour they wear on the combined board, and the
 *  same tiles and filter bar above it.
 *
 *  A seat is set here, by hand, from every משמרת's soldiers; the day is then
 *  blocked in that soldier's own משמרת and its commander is told. A duty
 *  already stood is recorded from "רישום תורנות שכבר נעשתה" -- it counts in
 *  fairness and statistics and blocks nothing. */
export function DutiesView({
  days, today, units, dark,
}: {
  days: string[];
  today: string;
  units: ComplexTeam[];
  dark: boolean;
}) {
  const start = days[0] ?? today;
  const end = days[days.length - 1] ?? today;
  const duties = useDuties(start, end);
  const [panel, setPanel] = useState<Panel>(null);
  const board = duties.board;
  const types = board?.types ?? [];
  const [filter, setFilter] = useState<DutyFilter>(NO_FILTER);
  const listed = types.filter((type) => type.active
    || board?.duties.some((duty) => duty.duty_type_id === type.id));
  const shown = listed.filter((type) => !filter.type || type.id === filter.type);
  const matches = (row: { team_id: string; employee: string }) =>
    (!filter.team || row.team_id === filter.team)
    && (!filter.soldier || `${row.team_id}:${row.employee}` === filter.soldier);
  // The palette of the whole מכלול roster, in the roster's order: a soldier
  // wears one colour here, whatever is filtered.
  const hueOf = useMemo(() => buildPalette(
    duties.roster.flatMap((team) => team.soldiers.map((soldier) => `${team.id}:${soldier.name}`)),
  ), [duties.roster]);

  const [suggestion, setSuggestion] = useState<DutySuggestion | null>(null);
  const [approval, setApproval] = useState<DutyApproval | null>(null);

  const onAll = (type: DutyType, date: string): ComplexDuty[] =>
    (board?.duties ?? []).filter((duty) => duty.duty_type_id === type.id && duty.duty_date === date);
  const proposedAll = (type: DutyType, date: string): DutyProposal[] =>
    (suggestion?.proposals ?? []).filter((row) => row.duty_type_id === type.id && row.duty_date === date);
  const figures = dutyFigures(shown, days, onAll, proposedAll);
  const rows = shown.filter((type) => !filter.openOnly
    || days.some((date) => openSeats(type, date, onAll(type, date), proposedAll(type, date)) > 0));

  const suggest = async () => {
    setApproval(null);
    setPanel(null);
    const result = await duties.suggest();
    if (result) setSuggestion(result);
  };
  const drop = (pick: DutyProposal) => setSuggestion((current) => current && {
    ...current, proposals: current.proposals.filter((row) => row !== pick),
  });
  const approve = async () => {
    if (!suggestion) return;
    const result = await duties.approve(suggestion.proposals.map((row) => ({
      duty_type_id: row.duty_type_id, team_id: row.team_id,
      employee: row.employee, duty_date: row.duty_date,
    })));
    if (result) {
      setSuggestion(null);
      setApproval(result);
    }
  };

  return (
    <div className="duties">
      <div className="board-coverage" role="group" aria-label="מצב התורנויות">
        <Tile icon={<CalendarCheck size={15} />} label="מקומות מאוישים"
          value={figures.seats ? `${figures.filled}/${figures.seats}` : "—"}
          detail={figures.seats ? `${Math.round((figures.filled / figures.seats) * 100)}% מהמקומות בטווח` : "אין תורנויות בטווח"}
          tone={figures.seats && figures.open === 0 ? "good" : "plain"} />
        <Tile icon={<UserMinus size={15} />} label="מקומות פנויים" value={`${figures.open}`}
          detail={figures.open ? "לחצו על + בתא כדי לשבץ" : "הכול מאויש"}
          tone={figures.open ? "attention" : "good"} />
        <Tile icon={<Users size={15} />} label="חיילים בתורנות" value={`${figures.soldiers}`}
          detail={`מ־${figures.teams} משמרות`} tone="plain" />
        <Tile icon={<Sparkles size={15} />} label="הצעות ממתינות" value={`${suggestion?.proposals.length ?? 0}`}
          detail={suggestion ? "עד האישור לא נשמר דבר" : "״מלא בהוגנות״ מציע"} tone={suggestion ? "attention" : "plain"} />
      </div>

      <div className="board-actions duty-toolbar" role="group" aria-label="פעולות התורנויות">
        <button type="button" className="ghost-button" onClick={() => setPanel({ kind: "types" })}>
          <Settings2 size={15} /> סוגי תורנויות
        </button>
        <button type="button" className="ghost-button" disabled={!types.length}
          onClick={() => setPanel({ kind: "record" })}>
          <History size={15} /> רישום תורנות שכבר נעשתה
        </button>
        <button type="button" className="ghost-button" onClick={() => setPanel({ kind: "balance" })}>
          <Scale size={15} /> מאזן
        </button>
        <button type="button" className="primary-button" disabled={duties.busy || !types.some((type) => type.active)}
          onClick={() => void suggest()}
          title="הצעה לכל המקומות הפנויים בטווח שעל המסך, במרווחים גדולים בין תורנויות של אותו חייל. שום דבר לא נשמר עד האישור.">
          <Sparkles size={15} /> מלא בהוגנות
        </button>
      </div>

      <DutySuggestionBar suggestion={suggestion} approval={approval} busy={duties.busy}
        onApprove={() => void approve()}
        onDiscard={() => { setSuggestion(null); setApproval(null); }} />

      {duties.error ? (
        <div className="error" role="alert">
          <AlertTriangle size={16} /><span>{duties.error}</span>
          <button type="button" className="icon-button subtle" onClick={duties.clearError} aria-label="סגירה">
            <X size={14} />
          </button>
        </div>
      ) : null}

      {panel?.kind === "balance" ? (
        <DutyBalancePanel start={start} end={end} today={today} onClose={() => setPanel(null)} />
      ) : panel?.kind === "types" ? (
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

      {listed.length ? (
        <DutyFilters types={listed} units={units} roster={duties.roster} filter={filter} onChange={setFilter} />
      ) : null}

      {board === null ? null : listed.length === 0 ? (
        <p className="cmd-empty">
          עדיין אין תורנויות במכלול. פתחו את &quot;סוגי תורנויות&quot; והוסיפו את הראשונה.
        </p>
      ) : rows.length === 0 ? (
        <p className="cmd-empty">אין תורנויות שמתאימות לסינון בטווח שעל המסך.</p>
      ) : (
        <div className="board-grid-wrap">
          <div className="board-grid-scroll">
            <div className="board-grid duty-board" style={{ "--board-days": days.length } as CSSProperties}
              role="table" aria-label="תורנויות המכלול">
              <div className="board-corner" role="columnheader">תורנות</div>
              {days.map((date) => (
                <div key={date} role="columnheader" className={[
                  "board-dayhead", date === today ? "is-today" : "", isWeekend(date) ? "is-weekend" : "",
                ].filter(Boolean).join(" ")}>
                  <span className="board-dayhead-weekday">{hebrewWeekday(date)}</span>
                  <span className="board-dayhead-date">{shortDate(date)}</span>
                  {date === today ? <span className="board-dayhead-pill">היום</span> : null}
                </div>
              ))}
              {rows.map((type) => (
                <div key={type.id} className="cmd-row" role="row">
                  <div className="board-rowhead" role="rowheader">
                    <span className="board-rowhead-name">{type.name}</span>
                    <span className="board-rowhead-hours">
                      {type.seats} ביום{type.weight !== 1 ? ` · שווה ${type.weight}` : ""}
                      {!type.active ? " · הושבתה" : ""}
                    </span>
                  </div>
                  {days.map((date) => (
                    <DutyCell key={date} type={type} date={date} today={today}
                      rows={onAll(type, date)} picks={proposedAll(type, date)}
                      visible={matches} dark={dark} hueOf={hueOf} onDrop={drop}
                      busy={duties.busy}
                      onAdd={() => setPanel({ kind: "assign", typeId: type.id, date })}
                      onCancel={(duty) => {
                        if (window.confirm(`לבטל את התורנות של ${duty.employee} ב־${displayDate(duty.duty_date)}?`)) {
                          void duties.cancel(duty.id);
                        }
                      }} />
                  ))}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

interface DutyFilter {
  type: string;
  team: string;
  soldier: string;
  openOnly: boolean;
}

const NO_FILTER: DutyFilter = { type: "", team: "", soldier: "", openOnly: false };

function openSeats(type: DutyType, date: string, rows: ComplexDuty[], picks: DutyProposal[]): number {
  if (!type.active || !runsOn(type, date)) return 0;
  return Math.max(0, type.seats - rows.filter((row) => row.blocks).length - picks.length);
}

/** The tiles' numbers over the duty types and days on screen. */
function dutyFigures(
  types: DutyType[], days: string[],
  on: (type: DutyType, date: string) => ComplexDuty[],
  proposed: (type: DutyType, date: string) => DutyProposal[],
) {
  let seats = 0;
  let filled = 0;
  let open = 0;
  const soldiers = new Set<string>();
  const teams = new Set<string>();
  for (const type of types) {
    for (const date of days) {
      const rows = on(type, date);
      rows.forEach((row) => { soldiers.add(`${row.team_id}:${row.employee}`); teams.add(row.team_id); });
      if (!type.active || !runsOn(type, date)) continue;
      const seated = rows.filter((row) => row.blocks).length;
      seats += type.seats;
      filled += Math.min(seated, type.seats);
      open += openSeats(type, date, rows, proposed(type, date));
    }
  }
  return { seats, filled, open, soldiers: soldiers.size, teams: teams.size };
}

/** The board's filter bar, for duties: a kind, a משמרת, one soldier, and
 *  "רק פנויים". It hides cards and rows; the tiles keep counting them. */
function DutyFilters({
  types, units, roster, filter, onChange,
}: {
  types: DutyType[];
  units: ComplexTeam[];
  roster: { id: string; name: string; soldiers: { name: string }[] }[];
  filter: DutyFilter;
  onChange: (next: DutyFilter) => void;
}) {
  const soldiers = roster
    .filter((team) => !filter.team || team.id === filter.team)
    .flatMap((team) => team.soldiers.map((soldier) => ({
      value: `${team.id}:${soldier.name}`, label: `${soldier.name} · ${team.name}`,
    })))
    .sort((a, b) => a.label.localeCompare(b.label, "he"));
  const active = Boolean(filter.type || filter.team || filter.soldier || filter.openOnly);
  const select = (label: string, value: string, all: string, options: { value: string; label: string }[],
    set: (value: string) => void) => (
    <label className="board-filter-field">
      <span className="board-filter-label">{label}</span>
      <select className="board-filter-select" value={value} onChange={(event) => set(event.target.value)}>
        <option value="">{all}</option>
        {options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
      </select>
    </label>
  );
  return (
    <div className="board-filters" role="group" aria-label="סינון התורנויות">
      <span className="board-filters-icon" aria-hidden="true"><Filter size={14} /></span>
      {select("תורנות", filter.type, "כל התורנויות", types.map((type) => ({ value: type.id, label: type.name })),
        (type) => onChange({ ...filter, type }))}
      {select("משמרת", filter.team, "כל המשמרות", units.map((unit) => ({ value: unit.id, label: unit.name })),
        (team) => onChange({ ...filter, team, soldier: team && !filter.soldier.startsWith(`${team}:`) ? "" : filter.soldier }))}
      {select("חייל", filter.soldier, "כל החיילים", soldiers, (soldier) => onChange({ ...filter, soldier }))}
      <div className="board-filter-toggles">
        <button type="button" className={`board-toggle${filter.openOnly ? " is-on" : ""}`}
          aria-pressed={filter.openOnly} onClick={() => onChange({ ...filter, openOnly: !filter.openOnly })}>
          <span aria-hidden="true"><UserMinus size={13} /></span> רק פנויים
        </button>
      </div>
      {active ? (
        <button type="button" className="board-filter-clear" onClick={() => onChange(NO_FILTER)} title="ניקוי כל הסינונים">
          <X size={13} /> ניקוי
        </button>
      ) : null}
    </div>
  );
}

function DutyCell({
  type, date, today, rows, picks, visible, dark, hueOf, busy, onAdd, onCancel, onDrop,
}: {
  type: DutyType;
  date: string;
  today: string;
  rows: ComplexDuty[];
  picks: DutyProposal[];
  visible: (row: { team_id: string; employee: string }) => boolean;
  dark: boolean;
  hueOf: (key: string) => number;
  onDrop: (pick: DutyProposal) => void;
  busy: boolean;
  onAdd: () => void;
  onCancel: (duty: ComplexDuty) => void;
}) {
  const runs = type.active && runsOn(type, date);
  const open = openSeats(type, date, rows, picks);
  const base = ["board-cell", "duty-cell", isWeekend(date) ? "is-weekend" : "", date === today ? "is-today" : ""];
  if (!runs && rows.length === 0) {
    return (
      <div role="cell" className={[...base, "is-absent"].join(" ")}>
        <span className="visually-hidden">התורנות לא פעילה ביום הזה</span>
      </div>
    );
  }
  return (
    <div role="cell" className={[...base, open ? "is-short" : ""].filter(Boolean).join(" ")}>
      {rows.filter(visible).map((row) => (
        <div key={row.id}
          className={`board-card cmd-card duty-card${row.blocks ? " is-published" : " is-record"}`}
          style={colorStyle(hueOf(`${row.team_id}:${row.employee}`), dark)}
          title={[row.team_name, row.note, row.blocks ? "" : "רישום בלבד: נספר, לא חוסם"].filter(Boolean).join(" · ")}>
          <div className="board-card-main">
            <span className="board-card-name">{row.employee}</span>
            <span className="board-card-role">{row.team_name}{row.blocks ? "" : " · רישום"}</span>
          </div>
          <button type="button" className="duty-card-remove" disabled={busy}
            onClick={() => onCancel(row)} aria-label={`ביטול התורנות של ${row.employee}`}>
            <X size={13} />
          </button>
        </div>
      ))}
      {picks.filter(visible).map((pick) => (
        <div key={`${pick.team_id}-${pick.employee}`} className="board-card cmd-card duty-card is-proposal"
          title={pick.reason}>
          <div className="board-card-main">
            <span className="board-card-name">{pick.employee}</span>
            <span className="board-card-role">{pick.team_name} · הצעה</span>
          </div>
          <button type="button" className="duty-card-remove" onClick={() => onDrop(pick)}
            aria-label={`הסרת ההצעה ${pick.employee}`}>
            <X size={13} />
          </button>
        </div>
      ))}
      {open ? (
        <>
          <span className="board-gap"><AlertTriangle size={11} /> {open > 1 ? `${open} פנויים` : "פנוי"}</span>
          <button type="button" className="board-add duty-add" disabled={busy} onClick={onAdd}
            aria-label={`שיבוץ ל${type.name} ב־${displayDate(date)}`} title="שיבוץ לתורנות">
            <Plus size={13} />
          </button>
        </>
      ) : null}
    </div>
  );
}
