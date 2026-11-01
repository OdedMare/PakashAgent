"use client";

import { AlertTriangle, X } from "lucide-react";
import { useMemo, useState } from "react";

import { DateInput, displayDate } from "@/components/DateInput";
import type { ComplexDuty, DutyConflict, DutyRosterTeam, DutyType } from "@/types";

/** Seat a soldier on a duty, or record one already stood.
 *
 *  Two modes of one form because they are one fact told at two times. A
 *  seat (`record` false) is a plan: the type must be running that day and
 *  have a free seat, and the day is blocked in the soldier's משמרת. A record
 *  is history -- a duty stood before this system, or outside it -- and only
 *  counts: in fairness and in statistics, never blocking a day. */
export function DutyForm({
  record,
  types,
  roster,
  duties,
  initialType,
  initialDate,
  busy,
  onSubmit,
  onClose,
}: {
  record: boolean;
  types: DutyType[];
  roster: DutyRosterTeam[];
  duties: ComplexDuty[];
  initialType: string;
  initialDate: string;
  busy: boolean;
  onSubmit: (input: { duty_type_id: string; team_id: string; employee: string; duty_date: string; note: string; blocks: boolean }) => Promise<DutyConflict[] | null>;
  onClose: () => void;
}) {
  const [typeId, setTypeId] = useState(initialType);
  const [date, setDate] = useState(initialDate);
  const [soldier, setSoldier] = useState("");
  const [note, setNote] = useState("");
  const [conflicts, setConflicts] = useState<{ who: string; rows: DutyConflict[] } | null>(null);

  const choosable = record ? types : types.filter((type) => type.active);
  // Who already stands a duty that day: one duty a day per soldier.
  const taken = useMemo(() => new Set(
    duties.filter((duty) => duty.duty_date === date).map((duty) => `${duty.team_id}|${duty.employee}`),
  ), [duties, date]);

  const submit = async () => {
    const [teamId, ...rest] = soldier.split("|");
    const employee = rest.join("|");
    const result = await onSubmit({
      duty_type_id: typeId, team_id: teamId, employee, duty_date: date, note, blocks: !record,
    });
    if (result === null) return;
    if (result.length) {
      setConflicts({ who: employee, rows: result });
      setSoldier("");
      setNote("");
    } else {
      onClose();
    }
  };

  return (
    <section className="duty-form" aria-label={record ? "רישום תורנות שכבר נעשתה" : "שיבוץ לתורנות"}>
      <header>
        <h3>{record ? "רישום תורנות שכבר נעשתה" : "שיבוץ לתורנות"}</h3>
        <button type="button" className="icon-button subtle" onClick={onClose} aria-label="סגירה">
          <X size={15} />
        </button>
      </header>
      <p className="cmd-hint">
        {record
          ? "תורנות שנעשתה לפני המערכת או מחוץ לה. נספרת בהוגנות ובסטטיסטיקה, ולא חוסמת שום יום בסידור."
          : "החייל/ת חסום/ה לכל היום במשמרת שלו/ה, וגם בלילה שלפני שמסתיים בבוקר. מפקד המשמרת מקבל הודעה."}
      </p>

      {conflicts ? (
        <div className="duty-conflicts" role="status">
          <AlertTriangle size={15} aria-hidden="true" />
          <div>
            <strong>התורנות נשמרה. {conflicts.who} כבר משובץ/ת במשמרות שהיא חוסמת:</strong>
            <ul>
              {conflicts.rows.map((row) => (
                <li key={`${row.date}-${row.shift_name}`}>
                  {displayDate(row.date)} · {row.shift_name}
                  {row.start_time ? ` ${row.start_time}–${row.end_time}` : ""}
                  {row.status === "published" ? " · שבוע שפורסם" : " · טיוטה"}
                </li>
              ))}
            </ul>
            <span>מפקד המשמרת קיבל הודעה וצריך למצוא מחליף.</span>
          </div>
        </div>
      ) : null}

      <form onSubmit={(event) => { event.preventDefault(); void submit(); }}>
        <label>
          <span>תורנות</span>
          <select value={typeId} onChange={(event) => setTypeId(event.target.value)} required>
            <option value="" disabled>בחירה…</option>
            {choosable.map((type) => (
              <option key={type.id} value={type.id}>{type.name}{type.active ? "" : " (לא פעילה)"}</option>
            ))}
          </select>
        </label>
        <label>
          <span>תאריך</span>
          <DateInput value={date} onChange={setDate} required />
        </label>
        <label>
          <span>חייל/ת</span>
          <select value={soldier} onChange={(event) => setSoldier(event.target.value)} required>
            <option value="" disabled>בחירה…</option>
            {roster.map((team) => (
              <optgroup key={team.id} label={team.name}>
                {team.soldiers
                  .filter((person) => !person.inactive_from || person.inactive_from > date)
                  .map((person) => {
                    const key = `${team.id}|${person.name}`;
                    return (
                      <option key={key} value={key} disabled={taken.has(key)}>
                        {person.name}{person.role ? ` · ${person.role}` : ""}{taken.has(key) ? " · כבר בתורנות ביום הזה" : ""}
                      </option>
                    );
                  })}
              </optgroup>
            ))}
          </select>
        </label>
        <label>
          <span>הערה</span>
          <input value={note} onChange={(event) => setNote(event.target.value)} maxLength={200}
            placeholder={record ? "למשל: לפני שהמערכת הופעלה" : "לא חובה"} />
        </label>
        <button type="submit" className="primary-button" disabled={busy || !typeId || !soldier || !date}>
          {record ? "רישום" : "שיבוץ"}
        </button>
      </form>
    </section>
  );
}
