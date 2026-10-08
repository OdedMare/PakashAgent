"use client";

import { Plus, Save, Trash2 } from "lucide-react";
import { useState } from "react";
import { updateProfile } from "@/services/api";
import type { RotationClosureWindow, RotationPresenceRule, WorkplaceProfile } from "@/types";

const CYCLES = { round: { label: "סבב", groups: ["א", "ב"] }, triplet: { label: "תלתון", groups: ["א", "ב", "ג"] } } as const;
const DAYS = ["ראשון", "שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת"];
const START_DAYS = ["ראשון", "שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת"];
const END_DAYS = ["שבת", "ראשון", "שני", "שלישי", "רביעי", "חמישי", "שישי"];

export function RotationSettings({ profile, onSaved }: { profile: WorkplaceProfile; onSaved: () => void | Promise<void> }) {
  const initial = profile.workplace ?? {};
  const [place, setPlace] = useState(initial);
  const [windows, setWindows] = useState<RotationClosureWindow[]>(initial.rotation_closure_windows ?? []);
  const [presence, setPresence] = useState<RotationPresenceRule[]>(initial.rotation_presence ?? []);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const shifts = (profile.shifts ?? []).map((row) => String((row as { name?: string }).name ?? "")).filter(Boolean);
  const set = (name: string, value: string) => setPlace((current) => ({ ...current, [name]: value }));
  const editWindow = (index: number, patch: Partial<RotationClosureWindow>) => setWindows((rows) => rows.map((row, i) => i === index ? { ...row, ...patch } : row));
  const editPresence = (index: number, patch: Partial<RotationPresenceRule>) => setPresence((rows) => rows.map((row, i) => i === index ? { ...row, ...patch } : row));
  const addWindow = (pattern: "round" | "triplet", group: string) => setWindows((rows) => [...rows, { pattern, group, start_day: -2, start_time: "12:00", end_day: 1, end_time: "12:00", starts_on: "", ends_on: "" }]);

  return <form className="rotation-settings" onSubmit={async (event) => {
    event.preventDefault();
    setSaving(true); setError(""); setMessage("");
    try {
      await updateProfile({ workplace: { ...place, rotation_closure_windows: windows, rotation_presence: presence } });
      await onSaved();
      setMessage("הגדרות הסבבים נשמרו. הן יחולו על השיבוץ הבא; סידור קיים לא נבנה מחדש.");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "שמירת הסבבים נכשלה"); }
    finally { setSaving(false); }
  }}>
    <div className="settings-content">
      <section className="settings-section">
        <h3>סבבים ותלתונים</h3>
        <p className="settings-note">לכל מחזור עוגן נפרד: בוחרים סוף שבוע וקבוצה שסוגרת בו. שאר הסגירות מתחלפות ממנו אוטומטית. זמני הנוכחות הם כללי חובה בשיבוץ.</p>
        <fieldset disabled={saving} className="rotation-settings-fields">
          {(Object.keys(CYCLES) as Array<keyof typeof CYCLES>).map((pattern) => {
            const cycle = CYCLES[pattern];
            const dateKey = `${pattern}_first_closure_date` as "round_first_closure_date" | "triplet_first_closure_date";
            const groupKey = `${pattern}_first_closure_group` as "round_first_closure_group" | "triplet_first_closure_group";
            const used = (profile.employees ?? []).some((row) => {
              const person = row as { exit_pattern?: string; rotation_group?: string };
              return (person.exit_pattern ?? initial.rotation_mode) === pattern && !!person.rotation_group;
            });
            const date = place[dateKey] ?? initial.first_closure_date ?? "";
            const group = place[groupKey] ?? initial.first_closure_group ?? "א";
            return <section className="rotation-cycle" key={pattern}>
              <h4>{cycle.label} {cycle.groups.join(" / ")}</h4>
              <div className="settings-input-row">
                <label>סוף שבוע עוגן<input className="settings-input" type="date" required={used} value={date} onChange={(e) => set(dateKey, e.target.value)} /></label>
                <label>מי סוגר בעוגן<select className="settings-input" value={(cycle.groups as readonly string[]).includes(group) ? group : "א"} onChange={(e) => set(groupKey, e.target.value)}>{cycle.groups.map((g) => <option key={g}>{g}</option>)}</select></label>
              </div>
              {used && !date ? <p className="form-error" role="status">יש להגדיר עוגן כדי לאפשר שיבוץ של {cycle.label}.</p> : null}
              {cycle.groups.map((group) => <article className="rotation-group" key={group}>
                <h5>{cycle.label} {group}</h5>
                <p className="settings-note">חלון הסגירה קובע מתי הקבוצה נשארת ומתי שאר קבוצות המחזור יוצאות. אפשר לשנות שעות גם לתקופה מסוימת.</p>
                {windows.map((row, index) => row.pattern === pattern && row.group === group ? <div className="rotation-settings-rule" key={index}>
                  <div className="settings-input-row">
                    <label>תחילת הסגירה<select className="settings-input" value={row.start_day} onChange={(e) => editWindow(index, { start_day: Number(e.target.value) })}>{START_DAYS.map((day, i) => <option key={day} value={i - 6}>{day}</option>)}</select></label>
                    <label>שעת התחלה<input className="settings-input" type="time" required value={row.start_time} onChange={(e) => editWindow(index, { start_time: e.target.value })} /></label>
                    <label>סיום הסגירה<select className="settings-input" value={row.end_day} onChange={(e) => editWindow(index, { end_day: Number(e.target.value) })}>{END_DAYS.map((day, i) => <option key={day} value={i}>{day}</option>)}</select></label>
                    <label>שעת חילוף / יציאה<input className="settings-input" type="time" required value={row.end_time} onChange={(e) => editWindow(index, { end_time: e.target.value })} /></label>
                  </div>
                  <DateRange startsOn={row.starts_on} endsOn={row.ends_on} onChange={(patch) => editWindow(index, patch)} />
                  <button className="ghost-button" type="button" onClick={() => setWindows((rows) => rows.filter((_, i) => i !== index))}><Trash2 size={14} /> הסרת חלון</button>
                </div> : null)}
                {!windows.some((row) => row.pattern === pattern && row.group === group) ? <p className="settings-note">ברירת המחדל: חמישי מתחילת היום עד סוף המשמרת הראשונה בראשון.</p> : null}
                <button className="ghost-button" type="button" onClick={() => addWindow(pattern, group)}><Plus size={14} /> הגדרת שעות סגירה / שינוי זמני</button>
                {presence.map((row, index) => row.pattern === pattern && row.group === group ? <div className="rotation-settings-rule" key={index}>
                  <label>נוכחות<select className="settings-input" value={String(row.available)} onChange={(e) => editPresence(index, { available: e.target.value === "true" })}><option value="false">לא נמצא — חסום לשיבוץ בשעות האלה</option><option value="true">נמצא רק בשעות האלה — מחליף את הסגירה בימים שנבחרו</option></select></label>
                  <div className="rotation-days" role="group" aria-label="ימי הנוכחות">{DAYS.map((day) => <label key={day}><input type="checkbox" checked={row.days.includes(day)} onChange={(e) => editPresence(index, { days: e.target.checked ? [...row.days, day] : row.days.filter((d) => d !== day) })} />{day}</label>)}</div>
                  <p className="settings-note">ללא בחירת ימים: כל הימים. ללא שעות: כל היום. אי־נוכחות גוברת על נוכחות כששני כללים חלים יחד.</p>
                  <div className="settings-input-row">
                    <label>משעה<input className="settings-input" type="time" value={row.start_time} onChange={(e) => editPresence(index, { start_time: e.target.value })} /></label>
                    <label>עד שעה<input className="settings-input" type="time" value={row.end_time} onChange={(e) => editPresence(index, { end_time: e.target.value })} /></label>
                  </div>
                  {shifts.length ? <div className="rotation-days" role="group" aria-label="משמרות הנוכחות">{shifts.map((shift) => <label key={shift}><input type="checkbox" checked={row.shifts.includes(shift)} onChange={(e) => editPresence(index, { shifts: e.target.checked ? [...row.shifts, shift] : row.shifts.filter((s) => s !== shift) })} />{shift}</label>)}</div> : null}
                  <p className="settings-note">ללא בחירת משמרות: כל המשמרות.</p>
                  <DateRange startsOn={row.starts_on} endsOn={row.ends_on} onChange={(patch) => editPresence(index, patch)} />
                  <label>הערה<input className="settings-input" value={row.reason} onChange={(e) => editPresence(index, { reason: e.target.value })} /></label>
                  <button className="ghost-button" type="button" onClick={() => setPresence((rows) => rows.filter((_, i) => i !== index))}><Trash2 size={14} /> הסרת כלל נוכחות</button>
                </div> : null)}
                <button className="ghost-button" type="button" onClick={() => setPresence((rows) => [...rows, { pattern, group, available: false, days: [], shifts: [], start_time: "", end_time: "", starts_on: "", ends_on: "", reason: "" }])}><Plus size={14} /> הוספת נוכחות / אי־נוכחות</button>
              </article>)}
            </section>;
          })}
        </fieldset>
        <p className="settings-note">שינוי עם תאריכי תחולה גובר על ההגדרה הקבועה. בחלונות סגירה, התחולה נבדקת לפי שבת של הסגירה. משמרת חייבת להתאים במלואה לשעות הנוכחות.</p>
      </section>
    </div>
    <footer className="settings-footer">
      {error ? <p className="form-error" role="alert">{error}</p> : null}
      {message ? <p className="form-success" role="status">{message}</p> : null}
      <button className="primary-button" type="submit" disabled={saving}><Save size={16} />{saving ? "שומר…" : "שמירת הסבבים"}</button>
    </footer>
  </form>;
}

function DateRange({ startsOn, endsOn, onChange }: { startsOn: string; endsOn: string; onChange: (patch: { starts_on?: string; ends_on?: string }) => void }) {
  return <div className="settings-input-row">
    <label>בתוקף מתאריך<input className="settings-input" type="date" value={startsOn} max={endsOn || undefined} onChange={(e) => onChange({ starts_on: e.target.value })} /></label>
    <label>בתוקף עד תאריך<input className="settings-input" type="date" value={endsOn} min={startsOn || undefined} onChange={(e) => onChange({ ends_on: e.target.value })} /></label>
  </div>;
}
