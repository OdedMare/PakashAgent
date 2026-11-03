"use client";

import { Plus, Trash2 } from "lucide-react";
import { useState } from "react";

import type { DutyType } from "@/types";

import { WEEKDAY_KEYS } from "./useDuties";

/** The מכלול's kinds of duty: name, soldiers a day, the weekdays it runs and
 *  how many shifts a day of it counts as. A kind with history is retired
 *  (`active: false`) rather than deleted -- deleting removes every
 *  assignment of it, past ones included, and says so before it does. */
export function DutyTypes({
  types,
  busy,
  onCreate,
  onUpdate,
  onDelete,
}: {
  types: DutyType[];
  busy: boolean;
  onCreate: (input: { name: string; seats: number; weight: number; days: string[] }) => Promise<unknown>;
  onUpdate: (id: string, patch: Partial<Omit<DutyType, "id">>) => Promise<unknown>;
  onDelete: (id: string) => Promise<unknown>;
}) {
  const [name, setName] = useState("");
  const [seats, setSeats] = useState(1);
  const [weight, setWeight] = useState(1);
  const [days, setDays] = useState<string[]>([]);

  const add = async () => {
    const created = await onCreate({ name: name.trim(), seats, weight, days });
    if (created) {
      setName("");
      setSeats(1);
      setWeight(1);
      setDays([]);
    }
  };

  return (
    <section className="duty-types" aria-label="סוגי התורנויות">
      <h3>סוגי התורנויות</h3>
      {types.length ? (
        <ul className="duty-type-list">
          {types.map((type) => (
            <li key={type.id} className={type.active ? "" : "is-retired"}>
              <span className="duty-type-name">{type.name}</span>
              <span className="duty-type-facts">
                {type.seats} ביום · {type.days.length ? type.days.join(", ") : "כל יום"}
                {" · "}{type.weight === 1 ? "נספרת כמשמרת" : `נספרת כ־${type.weight} משמרות`}
              </span>
              <button type="button" className="ghost-button" disabled={busy}
                onClick={() => void onUpdate(type.id, { active: !type.active })}>
                {type.active ? "השבתה" : "החזרה לפעילות"}
              </button>
              <button type="button" className="icon-button subtle" disabled={busy}
                aria-label={`מחיקת התורנות ${type.name}`}
                onClick={() => {
                  if (window.confirm(`למחוק את "${type.name}"? כל השיבוצים שלה יימחקו, גם בעבר. כדי לשמור את ההיסטוריה עדיף להשבית.`)) {
                    void onDelete(type.id);
                  }
                }}>
                <Trash2 size={14} />
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="cmd-empty">עדיין אין תורנויות. הוסיפו את הראשונה כאן.</p>
      )}

      <form className="duty-type-form" onSubmit={(event) => { event.preventDefault(); void add(); }}>
        <label>
          <span>שם</span>
          <input value={name} onChange={(event) => setName(event.target.value)}
            placeholder="מטבח, שמירה, ש״ג…" maxLength={40} required />
        </label>
        <label>
          <span>חיילים ביום</span>
          <input type="number" min={1} max={50} value={seats}
            onChange={(event) => setSeats(Number(event.target.value) || 1)} />
        </label>
        <label>
          <span>נספרת כמה משמרות</span>
          <input type="number" min={0} max={5} value={weight}
            onChange={(event) => setWeight(Math.max(0, Number(event.target.value) || 0))} />
        </label>
        <fieldset className="duty-days">
          <legend>ימים (בלי סימון: כל יום)</legend>
          {WEEKDAY_KEYS.map((day) => (
            <label key={day} className="duty-day">
              <input type="checkbox" checked={days.includes(day)}
                onChange={(event) => setDays((current) => event.target.checked
                  ? [...current, day] : current.filter((item) => item !== day))} />
              <span>{day}</span>
            </label>
          ))}
        </fieldset>
        <button type="submit" className="primary-button" disabled={busy || !name.trim()}>
          <Plus size={15} /> הוספת תורנות
        </button>
      </form>
    </section>
  );
}
