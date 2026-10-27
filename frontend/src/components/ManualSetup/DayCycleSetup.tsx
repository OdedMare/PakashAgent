"use client";

import { Plus, Trash2 } from "lucide-react";

import { DateInput } from "@/components/DateInput";
import { DAY_CYCLE_PRESETS, GROUP_LETTERS, defaultOffset, groupOffset, newDayCycle } from "@/lib/dayCycles";
import type { DayCycle, DayCycleTimeChange, DayCycleTiming } from "@/types";

import { CyclePreview, TimingFields, addDays } from "./DayCycleTiming";
import { Field } from "./fields";

/** Day-based cycles: 11/3, 12/2, שבוע־שבוע, or any N days on base and M home.
 *
 *  One anchor (the day group א starts on base) places every group; the others
 *  start a stated number of days later, spread evenly unless the manager says
 *  otherwise. Hours come in three layers — the cycle, a group, a date range —
 *  and each layer states only what it changes. */
export function DayCycleSetup({
  cycles,
  onChange,
  used,
}: {
  cycles: DayCycle[];
  onChange: React.Dispatch<React.SetStateAction<DayCycle[]>>;
  /** Cycle ids somebody on the roster is on; those cannot be deleted. */
  used: Set<string>;
}) {
  const edit = (id: string, patch: Partial<DayCycle>) =>
    onChange((rows) => rows.map((row) => row.id === id ? { ...row, ...patch } : row));
  return (
    <div className="rotation-cycles" aria-label="מחזורי ימים">
      {cycles.map((cycle) => (
        <DayCycleCard key={cycle.id} cycle={cycle} inUse={used.has(cycle.id)}
          onEdit={(patch) => edit(cycle.id, patch)}
          onRemove={() => onChange((rows) => rows.filter((row) => row.id !== cycle.id))} />
      ))}
      <button type="button" className="ghost-button" onClick={() => onChange((rows) => [...rows, newDayCycle(rows)])}>
        <Plus size={16} /> הוספת מחזור ימים (11/3, 12/2, שבוע־שבוע…)
      </button>
    </div>
  );
}

function DayCycleCard({ cycle, inUse, onEdit, onRemove }: {
  cycle: DayCycle;
  inUse: boolean;
  onEdit: (patch: Partial<DayCycle>) => void;
  onRemove: () => void;
}) {
  const length = cycle.base_days + cycle.home_days;
  const autoName = DAY_CYCLE_PRESETS.some((preset) => preset.label === cycle.name) || /^\d+\/\d+$/.test(cycle.name);
  const setDays = (base: number, home: number, label?: string) =>
    onEdit({ base_days: base, home_days: home, offsets: {}, ...(autoName ? { name: label ?? `${base}/${home}` } : {}) });
  // The nominal transition days of a group's first stretch, so the options
  // can name a weekday. Group א's stand for the cycle's own hours.
  const nominal = (group: string, days: number) =>
    cycle.anchor_date ? addDays(cycle.anchor_date, groupOffset(cycle, group) + days) : undefined;
  const leaveDay = nominal(cycle.groups[0], cycle.base_days);
  const returnDay = nominal(cycle.groups[0], length);
  const timing = (patch: DayCycleTiming) => onEdit(patch);
  const groupTiming = (group: string, patch: DayCycleTiming) =>
    onEdit({ group_times: { ...cycle.group_times, [group]: clean({ ...cycle.group_times[group], ...patch }) } });
  const editChange = (index: number, patch: Partial<DayCycleTimeChange>) =>
    onEdit({ time_changes: cycle.time_changes.map((row, i) => i === index ? { ...row, ...patch } : row) });

  return (
    <article className="rotation-cycle-card is-day-cycle">
      <div className="rotation-rule-head">
        <div className="manual-grid three">
          <Field label="שם המחזור"><input value={cycle.name} maxLength={40} onChange={(event) => onEdit({ name: event.target.value })} /></Field>
        </div>
        <button type="button" className="icon-button subtle" aria-label={`מחיקת ${cycle.name}`} disabled={inUse}
          title={inUse ? "יש אנשי צוות במחזור הזה" : undefined} onClick={onRemove}><Trash2 size={15} /></button>
      </div>

      <div className="day-cycle-presets" role="group" aria-label="תבניות">
        {DAY_CYCLE_PRESETS.map((preset) => (
          <button type="button" key={preset.label}
            className={`chip-button${preset.base === cycle.base_days && preset.home === cycle.home_days ? " is-selected" : ""}`}
            onClick={() => setDays(preset.base, preset.home, preset.label)}>{preset.label}</button>
        ))}
      </div>

      <div className="manual-grid rotation-window-grid">
        <Field label="ימים בבסיס"><input type="number" min={1} max={119} value={cycle.base_days} onChange={(event) => setDays(Math.max(1, Number(event.target.value) || 1), cycle.home_days)} /></Field>
        <Field label="ימים בבית"><input type="number" min={1} max={119} value={cycle.home_days} onChange={(event) => setDays(cycle.base_days, Math.max(1, Number(event.target.value) || 1))} /></Field>
        <Field label="עוגן — היום שבו א׳ נכנסת לבסיס"><DateInput value={cycle.anchor_date} onChange={(iso) => onEdit({ anchor_date: iso })} /></Field>
        <Field label="מספר קבוצות">
          <select value={cycle.groups.length} onChange={(event) => onEdit({ groups: GROUP_LETTERS.slice(0, Number(event.target.value)), offsets: {}, group_times: {}, time_changes: cycle.time_changes.map((row) => ({ ...row, group: "" })) })}>
            {GROUP_LETTERS.map((_, i) => <option key={i} value={i + 1}>{i + 1}</option>)}
          </select>
        </Field>
      </div>
      {!cycle.anchor_date ? <p className="rotation-derived-note is-warning" role="status">בלי עוגן אי אפשר לבנות סידור לאנשי המחזור.</p> : null}

      {cycle.groups.length > 1 ? (
        <section className="rotation-block">
          <header><strong>מתי כל קבוצה נכנסת</strong><span>ברירת המחדל מפזרת את הקבוצות שווה על המחזור. כדי ש־ב׳ תיכנס בדיוק כש־א׳ יוצאת, הקלידו {cycle.base_days}.</span></header>
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
        </section>
      ) : null}

      <section className="rotation-block">
        <header><strong>שעות יציאה וחזרה</strong><span>יום המעבר הוא היום הראשון בבית (יציאה) והיום הראשון בבסיס (חזרה). אפשר להקדים או לאחר אותו עד שלושה ימים ולקבוע שעה.</span></header>
        <TimingFields value={cycle} onChange={timing} leaveDay={leaveDay} returnDay={returnDay} />
        {cycle.groups.length > 1 ? cycle.groups.map((group) => {
          const own = cycle.group_times[group];
          return own ? (
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
        }) : null}
        <div className="day-cycle-presets">
          {cycle.groups.length > 1 ? cycle.groups.filter((group) => !cycle.group_times[group]).map((group) => (
            <button type="button" className="ghost-button" key={group} onClick={() => onEdit({ group_times: { ...cycle.group_times, [group]: {} } })}><Plus size={16} /> שעות שונות ל־{group}׳</button>
          )) : null}
          <button type="button" className="ghost-button" onClick={() => onEdit({ time_changes: [...cycle.time_changes, { group: "", starts_on: "", ends_on: "" }] })}><Plus size={16} /> שינוי שעות לתאריכים</button>
        </div>
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
      </section>

      <CyclePreview cycle={cycle} />
    </article>
  );
}

/** A layer keeps only the fields it states. */
function clean(timing: DayCycleTiming): DayCycleTiming {
  return Object.fromEntries(Object.entries(timing).filter(([, value]) => value !== undefined && value !== "")) as DayCycleTiming;
}
