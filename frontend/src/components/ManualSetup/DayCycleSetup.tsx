"use client";

import { Plus, Trash2 } from "lucide-react";

import { DateInput } from "@/components/DateInput";
import { GROUP_LETTERS, defaultOffset, groupOffset, presetOf } from "@/lib/dayCycles";
import type { DayCycle, DayCycleTimeChange, DayCycleTiming } from "@/types";

import { TimingFields, addDays } from "./DayCycleTiming";
import { Field } from "./fields";

/** The questions of each day cycle chosen in the exits list (11/3, 12/2,
 *  שבוע־שבוע, or other days on base and at home).
 *
 *  Which cycles exist is the list's choice, so a card has no name, no
 *  presets and no delete: it asks for the anchor (the day group א starts on
 *  base), how many groups, and the departure and return. Per-group starts
 *  and hours and dated changes are folded away, since most units never
 *  state them. */
export function DayCycleSetup({ cycles, onChange }: {
  cycles: DayCycle[];
  onChange: React.Dispatch<React.SetStateAction<DayCycle[]>>;
}) {
  const edit = (id: string, patch: Partial<DayCycle>) =>
    onChange((rows) => rows.map((row) => row.id === id ? { ...row, ...patch } : row));
  return (
    <div className="rotation-cycles" aria-label="מחזורי ימים">
      {cycles.map((cycle) => <DayCycleCard key={cycle.id} cycle={cycle} onEdit={(patch) => edit(cycle.id, patch)} />)}
    </div>
  );
}

function DayCycleCard({ cycle, onEdit }: { cycle: DayCycle; onEdit: (patch: Partial<DayCycle>) => void }) {
  const length = cycle.base_days + cycle.home_days;
  const custom = !presetOf(cycle);
  // A name that only states the days follows them; a unit's own name stays.
  const setDays = (base: number, home: number) =>
    onEdit({ base_days: base, home_days: home, offsets: {}, ...(/^\d+\/\d+$/.test(cycle.name) ? { name: `${base}/${home}` } : {}) });
  // The nominal transition days of a group's first stretch, so the options
  // can name a weekday. Group א's stand for the cycle's own hours.
  const nominal = (group: string, days: number) =>
    cycle.anchor_date ? addDays(cycle.anchor_date, groupOffset(cycle, group) + days) : undefined;
  const groupTiming = (group: string, patch: DayCycleTiming) =>
    onEdit({ group_times: { ...cycle.group_times, [group]: clean({ ...cycle.group_times[group], ...patch }) } });
  const editChange = (index: number, patch: Partial<DayCycleTimeChange>) =>
    onEdit({ time_changes: cycle.time_changes.map((row, i) => i === index ? { ...row, ...patch } : row) });
  const adjustments = Object.keys(cycle.offsets).length + Object.keys(cycle.group_times).length + cycle.time_changes.length;

  return (
    <article className="rotation-cycle-card is-day-cycle">
      <header>
        <strong>{cycle.name || `${cycle.base_days}/${cycle.home_days}`}</strong>
        <span>{cycle.base_days} ימים בבסיס, {cycle.home_days} בבית. יום היציאה הוא היום הראשון בבית, יום החזרה הוא היום הראשון בבסיס.</span>
      </header>

      <div className="manual-grid rotation-window-grid">
        {custom ? <>
          <Field label="ימים בבסיס"><input type="number" min={1} max={119} value={cycle.base_days} onChange={(event) => setDays(Math.max(1, Number(event.target.value) || 1), cycle.home_days)} /></Field>
          <Field label="ימים בבית"><input type="number" min={1} max={119} value={cycle.home_days} onChange={(event) => setDays(cycle.base_days, Math.max(1, Number(event.target.value) || 1))} /></Field>
        </> : null}
        <Field label="עוגן — היום שבו א׳ נכנסת לבסיס"><DateInput value={cycle.anchor_date} onChange={(iso) => onEdit({ anchor_date: iso })} /></Field>
        <Field label="מספר קבוצות">
          <select value={cycle.groups.length} onChange={(event) => onEdit({ groups: GROUP_LETTERS.slice(0, Number(event.target.value)), offsets: {}, group_times: {}, time_changes: cycle.time_changes.map((row) => ({ ...row, group: "" })) })}>
            {GROUP_LETTERS.map((_, i) => <option key={i} value={i + 1}>{i + 1}</option>)}
          </select>
        </Field>
      </div>
      {!cycle.anchor_date ? <p className="rotation-derived-note is-warning" role="status">בלי עוגן אי אפשר לבנות סידור לאנשי המחזור.</p> : null}

      <TimingFields value={cycle} onChange={onEdit} leaveDay={nominal(cycle.groups[0], cycle.base_days)} returnDay={nominal(cycle.groups[0], length)} />

      <details className="day-cycle-more">
        <summary>התאמות לפי קבוצה ותאריך{adjustments ? ` (${adjustments})` : ""}</summary>
        {cycle.groups.length > 1 ? (
          <div className="manual-grid rotation-window-grid">
            {cycle.groups.slice(1).map((group) => (
              <Field key={group} label={`${group}׳ נכנסת — ימים אחרי א׳`}>
                <input type="number" min={0} max={length - 1} placeholder={String(defaultOffset(cycle, group))}
                  value={cycle.offsets[group] ?? ""}
                  onChange={(event) => {
                    const { [group]: _drop, ...rest } = cycle.offsets;
                    onEdit({ offsets: event.target.value === "" ? rest : { ...rest, [group]: Math.min(length - 1, Math.max(0, Number(event.target.value))) } });
                  }} />
              </Field>
            ))}
          </div>
        ) : null}
        {cycle.groups.map((group) => {
          const own = cycle.group_times[group];
          return own && cycle.groups.length > 1 ? (
            <article className="manual-row rotation-rule" key={group}>
              <div className="rotation-rule-head">
                <div><strong>שעות של {group}׳</strong><span>גוברות על שעות המחזור, רק לקבוצה הזו.</span></div>
                <button type="button" className="icon-button subtle" aria-label={`הסרת השעות של ${group}`} onClick={() => {
                  const { [group]: _drop, ...rest } = cycle.group_times;
                  onEdit({ group_times: rest });
                }}><Trash2 size={15} /></button>
              </div>
              <TimingFields partial value={own} onChange={(patch) => groupTiming(group, patch)}
                leaveDay={nominal(group, cycle.base_days)} returnDay={nominal(group, length)} />
            </article>
          ) : null;
        })}
        {cycle.time_changes.map((row, index) => (
          <article className="manual-row rotation-rule" key={index}>
            <div className="rotation-rule-head">
              <div><strong>שינוי זמני</strong><span>חל על יציאות שיום המעבר שלהן בטווח — למשל חג או אירוע.</span></div>
              <button type="button" className="icon-button subtle" aria-label="הסרת השינוי" onClick={() => onEdit({ time_changes: cycle.time_changes.filter((_, i) => i !== index) })}><Trash2 size={15} /></button>
            </div>
            <div className="manual-grid three">
              <Field label="קבוצה"><select value={row.group} onChange={(event) => editChange(index, { group: event.target.value })}><option value="">כל הקבוצות</option>{cycle.groups.map((group) => <option key={group} value={group}>{group}׳</option>)}</select></Field>
              <Field label="מתאריך"><DateInput value={row.starts_on} max={row.ends_on || undefined} onChange={(iso) => editChange(index, { starts_on: iso })} /></Field>
              <Field label="עד תאריך (רשות)"><DateInput value={row.ends_on} min={row.starts_on || undefined} onChange={(iso) => editChange(index, { ends_on: iso })} /></Field>
            </div>
            <TimingFields partial value={row} onChange={(patch) => editChange(index, patch)} />
          </article>
        ))}
        <div className="day-cycle-actions">
          {cycle.groups.length > 1 ? cycle.groups.filter((group) => !cycle.group_times[group]).map((group) => (
            <button type="button" className="ghost-button" key={group} onClick={() => onEdit({ group_times: { ...cycle.group_times, [group]: {} } })}><Plus size={16} /> שעות שונות ל־{group}׳</button>
          )) : null}
          <button type="button" className="ghost-button" onClick={() => onEdit({ time_changes: [...cycle.time_changes, { group: "", starts_on: "", ends_on: "" }] })}><Plus size={16} /> שינוי שעות לתאריכים</button>
        </div>
      </details>
    </article>
  );
}

/** A layer keeps only the fields it states. */
function clean(timing: DayCycleTiming): DayCycleTiming {
  return Object.fromEntries(Object.entries(timing).filter(([, value]) => value !== undefined && value !== "")) as DayCycleTiming;
}
