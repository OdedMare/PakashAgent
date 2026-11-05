"use client";

import { Plus, Trash2 } from "lucide-react";

import { DateInput } from "@/components/DateInput";
import { GROUP_LETTERS, WEEKEND_GROUPS, defaultOffset, groupOffset, isWeekends, newDayCycle, newWeekendCycle, weekendDays } from "@/lib/dayCycles";
import type { DayCycle, DayCycleTimeChange, DayCycleTiming } from "@/types";

import { TimingFields, addDays } from "./DayCycleTiming";
import { saturdayOf } from "./closureShapes";
import { Field } from "./fields";

/** The day cycles chosen in the exits list (11/3, 12/2, שבוע־שבוע, a manual
 *  days-on-base/days-home, a 1 ל־X), one card each.
 *
 *  A card edits its exit — the name, the days or the X, the anchor, the
 *  groups and the departure and return — and deletes it, unless somebody on
 *  the roster is on it. Per-group starts and hours and dated changes are
 *  folded away, since most units never state them. More manual exits than
 *  the list's one each are added below the cards. */
export function DayCycleSetup({ cycles, onChange, used }: {
  cycles: DayCycle[];
  onChange: React.Dispatch<React.SetStateAction<DayCycle[]>>;
  /** Cycle ids somebody on the roster is on; those cannot be deleted. */
  used: Set<string>;
}) {
  const edit = (id: string, patch: Partial<DayCycle>) =>
    onChange((rows) => rows.map((row) => row.id === id ? { ...row, ...patch } : row));
  return (
    <div className="rotation-cycles" aria-label="מחזורי יציאות">
      {cycles.map((cycle) => (
        <DayCycleCard key={cycle.id} cycle={cycle} inUse={used.has(cycle.id)}
          onEdit={(patch) => edit(cycle.id, patch)}
          onRemove={() => onChange((rows) => rows.filter((row) => row.id !== cycle.id))} />
      ))}
      <div className="day-cycle-actions">
        <button type="button" className="ghost-button" onClick={() => onChange((rows) => [...rows, newDayCycle(rows, 9, 5)])}><Plus size={16} /> מחזור ימים ידני</button>
        <button type="button" className="ghost-button" onClick={() => onChange((rows) => [...rows, newWeekendCycle(rows)])}><Plus size={16} /> סגירה 1 ל־X</button>
      </div>
    </div>
  );
}

// A name that only states the days, or the X, follows them; a unit's own name stays.
const AUTO_NAME = /^(\d+\/\d+|1 ל־\d+)$/;

function DayCycleCard({ cycle, inUse, onEdit, onRemove }: {
  cycle: DayCycle;
  inUse: boolean;
  onEdit: (patch: Partial<DayCycle>) => void;
  onRemove: () => void;
}) {
  const weekends = isWeekends(cycle);
  const length = cycle.base_days + cycle.home_days;
  const autoName = AUTO_NAME.test(cycle.name) || !cycle.name;
  const setDays = (base: number, home: number) =>
    onEdit({ base_days: base, home_days: home, offsets: {}, ...(autoName ? { name: `${base}/${home}` } : {}) });
  const setGroups = (count: number) => onEdit({
    ...(weekends ? weekendDays(count) : { groups: GROUP_LETTERS.slice(0, count) }),
    ...(weekends && autoName ? { name: `1 ל־${count}` } : {}),
    offsets: {}, group_times: {}, time_changes: cycle.time_changes.map((row) => ({ ...row, group: "" })),
  });
  // The nominal transition days, so the options can name a weekday: a
  // stretch's first home and first base day, or a 1 ל־X's Thursday and Sunday.
  const saturday = cycle.anchor_date ? saturdayOf(cycle.anchor_date) : "";
  const nominal = (group: string, days: number) =>
    cycle.anchor_date ? addDays(cycle.anchor_date, groupOffset(cycle, group) + days) : undefined;
  const leaveOf = (group: string) => weekends ? (saturday ? addDays(saturday, -2) : undefined) : nominal(group, cycle.base_days);
  const returnOf = (group: string) => weekends ? (saturday ? addDays(saturday, 1) : undefined) : nominal(group, length);
  const groupTiming = (group: string, patch: DayCycleTiming) =>
    onEdit({ group_times: { ...cycle.group_times, [group]: clean({ ...cycle.group_times[group], ...patch }) } });
  const editChange = (index: number, patch: Partial<DayCycleTimeChange>) =>
    onEdit({ time_changes: cycle.time_changes.map((row, i) => i === index ? { ...row, ...patch } : row) });
  const adjustments = (weekends ? 0 : Object.keys(cycle.offsets).length) + Object.keys(cycle.group_times).length + cycle.time_changes.length;
  const counts = weekends
    ? Array.from({ length: WEEKEND_GROUPS.max - WEEKEND_GROUPS.min + 1 }, (_, i) => i + WEEKEND_GROUPS.min)
    : GROUP_LETTERS.map((_, i) => i + 1);

  return (
    <article className="rotation-cycle-card is-day-cycle">
      <div className="rotation-rule-head">
        <div>
          <strong>{cycle.name || (weekends ? `1 ל־${cycle.groups.length}` : `${cycle.base_days}/${cycle.home_days}`)}</strong>
          <span>{weekends
            ? `${cycle.groups.length} קבוצות, כל שבת קבוצה אחת סוגרת לפי הסדר והשאר בבית מחמישי עד ראשון.`
            : "יום היציאה הוא היום הראשון בבית, יום החזרה הוא היום הראשון בבסיס."}</span>
        </div>
        <button type="button" className="icon-button subtle" aria-label={`מחיקת ${cycle.name}`} disabled={inUse}
          title={inUse ? "יש אנשי צוות ביציאה הזו — מעבירים אותם קודם" : "מחיקה"} onClick={onRemove}><Trash2 size={15} /></button>
      </div>

      <div className="manual-grid rotation-window-grid">
        <Field label="שם"><input value={cycle.name} maxLength={40} onChange={(event) => onEdit({ name: event.target.value })} /></Field>
        {weekends ? null : <>
          <Field label="ימים בבסיס"><input type="number" min={1} max={119} value={cycle.base_days} onChange={(event) => setDays(Math.max(1, Number(event.target.value) || 1), cycle.home_days)} /></Field>
          <Field label="ימים בבית"><input type="number" min={1} max={119} value={cycle.home_days} onChange={(event) => setDays(cycle.base_days, Math.max(1, Number(event.target.value) || 1))} /></Field>
        </>}
        <Field label={weekends ? "סגירה אחת מכל — שבתות (X)" : "מספר קבוצות"}>
          <select value={cycle.groups.length} onChange={(event) => setGroups(Number(event.target.value))}>
            {counts.map((count) => <option key={count} value={count}>{weekends ? `1 ל־${count} · ${count} קבוצות` : count}</option>)}
          </select>
        </Field>
        <Field label={weekends ? "עוגן — שבת שבה א׳ סוגרת" : "עוגן — היום שבו א׳ נכנסת לבסיס"}><DateInput value={cycle.anchor_date} onChange={(iso) => onEdit({ anchor_date: iso })} /></Field>
      </div>
      {!cycle.anchor_date ? <p className="rotation-derived-note is-warning" role="status">בלי עוגן אי אפשר לבנות סידור לאנשי המחזור.</p> : null}

      <TimingFields value={cycle} onChange={onEdit} leaveDay={leaveOf(cycle.groups[0])} returnDay={returnOf(cycle.groups[0])} />

      <details className="day-cycle-more">
        <summary>התאמות לפי קבוצה ותאריך{adjustments ? ` (${adjustments})` : ""}</summary>
        {cycle.groups.length > 1 && !weekends ? (
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
                leaveDay={leaveOf(group)} returnDay={returnOf(group)} />
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
