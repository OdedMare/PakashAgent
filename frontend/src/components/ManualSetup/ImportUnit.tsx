"use client";

import { useEffect, useState } from "react";
import { previewUnitImport } from "@/services/api";
import type { UnitImportPreview } from "@/services/api";
import { TimeInput } from "@/components/TimeInput";
import { Field } from "./fields";

type Row = Record<string, unknown>;
type Person = { name: string; target: string; include: boolean; candidates: string[]; sources: string[] };
type Shift = UnitImportPreview["shifts"][number] & { include: boolean; replace: boolean };
type Draft = { step: number; result: UnitImportPreview; people: Person[]; shifts: Shift[] };
const STEPS = ["העלאת קובץ", "בדיקת הזיהוי", "חיילים", "משמרות", "סקירה ואישור"];

export function ImportUnit({ teamId, onApply, onClose }: {
  teamId: string; onApply: (people: Row[], shifts: Row[]) => void; onClose: () => void;
}) {
  const key = `unit-import:${teamId}`;
  const [draft, setDraft] = useState<Draft | null>(() => {
    try { const saved = sessionStorage.getItem(key); return saved ? JSON.parse(saved) : null; }
    catch { return null; }
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    try { if (draft) sessionStorage.setItem(key, JSON.stringify(draft)); else sessionStorage.removeItem(key); } catch { /* Editing remains available without browser storage. */ }
  }, [draft, key]);

  async function read(file: File) {
    setBusy(true); setError("");
    try {
      const result = await previewUnitImport(file);
      setDraft({ step: 1, result,
        people: result.people.map((p) => ({ ...p, target: p.existing || p.name, include: true })),
        shifts: result.shifts.map((s) => ({ ...s, include: true, replace: false })),
      });
    } catch (reason) { setError(reason instanceof Error ? reason.message : "קריאת הקובץ נכשלה"); }
    finally { setBusy(false); }
  }
  const step = draft?.step ?? 0;
  const people = draft?.people.filter((p) => p.include && p.target.trim()) ?? [];
  const shifts = draft?.shifts.filter((s) => s.include && s.name.trim()) ?? [];
  const invalid = shifts.some((s) => (!s.existing || s.replace) &&
    (!/^([01]\d|2[0-3]):[0-5]\d$/.test(s.start_time) || !/^([01]\d|2[0-3]):[0-5]\d$/.test(s.end_time)
      || !Number.isInteger(s.headcount) || s.headcount < 0 || s.headcount > 100));
  const updatePerson = (index: number, patch: Partial<Person>) => setDraft((d) => d && ({ ...d, people: d.people.map((p, i) => i === index ? { ...p, ...patch } : p) }));
  const updateShift = (index: number, patch: Partial<Shift>) => setDraft((d) => d && ({ ...d, shifts: d.shifts.map((s, i) => i === index ? { ...s, ...patch } : s) }));

  return <section className="unit-import" aria-label="ייבוא הגדרת יחידה" aria-busy={busy}>
    <header><div><h2>הגדרת יחידה מאקסל</h2><p>מחלצים חיילים ומשמרות, בודקים יחד ומעבירים לטופס ההגדרה.</p></div>
      <button type="button" className="ghost-button" disabled={busy} onClick={onClose}>סגירת האשף</button></header>
    <ol className="unit-import-steps">{STEPS.map((label, i) => <li key={label} aria-current={i === step ? "step" : undefined}>{label}</li>)}</ol>
    {error && <p role="alert" className="manual-error">{error}</p>}
    <div aria-live="polite">{busy && <p>קורא את הגיליונות ומחלץ את הגדרת היחידה…</p>}</div>
    {step === 0 && <Field label="קובץ Excel או CSV, עד 20MB">
      <input type="file" accept=".xlsx,.csv,.tsv" disabled={busy} onChange={(e) => { const file = e.target.files?.[0]; if (file) void read(file); e.target.value = ""; }} />
      <p>אין צורך בתבנית קבועה. אפשר להעלות רשימות או טבלת שיבוץ קיימת. הטיוטה נשמרת בכרטיסייה זו.</p>
    </Field>}
    {draft && step === 1 && <>
      <p>{draft.result.filename}: זוהו {draft.people.length} שמות ו־{draft.shifts.length} משמרות.</p>
      {draft.result.sheets.map((sheet) => <details key={sheet.name}><summary>{sheet.name || "גיליון"} · {sheet.rows} שורות · {sheet.recognized ? "נמצא מידע" : "נדרשת השלמה ידנית"}</summary>
        <div className="unit-import-table"><table><tbody>{sheet.preview.map((row, i) => <tr key={i}>{row.map((cell, j) => <td key={j}>{cell}</td>)}</tr>)}</tbody></table></div>
      </details>)}
      <ul>{draft.result.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>
      <p>אפשר להמשיך גם עם חילוץ חלקי ולהשלים בשלבים הבאים.</p>
    </>}
    {draft && step === 2 && <>
      <p>שמות זהים אוחדו. בחרו שם קיים כשמדובר באותו חייל, או השאירו את השם להוספה. חיילים קיימים לא יימחקו.</p>
      {draft.people.map((person, i) => <div className="manual-row" key={i}>
        <label className="manual-check"><input type="checkbox" checked={person.include} onChange={(e) => updatePerson(i, { include: e.target.checked })} />{person.name || "חייל חדש"}</label>
        <Field label="שם לשמירה"><input value={person.target} maxLength={200} onChange={(e) => updatePerson(i, { target: e.target.value })} /></Field>
        <small>מקור: {person.sources.join(", ") || "הוספה ידנית"}</small>
        {person.candidates.length > 0 && <Field label="התאמה לחייל קיים"><select value={person.candidates.includes(person.target) ? person.target : ""} onChange={(e) => updatePerson(i, { target: e.target.value || person.name })}>
          <option value="">הוספה בשם המקורי</option>{person.candidates.map((name) => <option key={name}>{name}</option>)}
        </select></Field>}
      </div>)}
      <button type="button" className="ghost-button" onClick={() => setDraft({ ...draft, people: [...draft.people, { name: "", target: "", include: true, sources: [], candidates: [] }] })}>הוספת חייל/ת</button>
    </>}
    {draft && step === 3 && <>
      <p>בדקו את השעות והתקנים שהוצעו. הגדרות משמרת קיימת נשמרות, אלא אם בחרתם לעדכן אותה.</p>
      {draft.shifts.map((shift, i) => <div className="manual-row" key={i}>
        <label className="manual-check"><input type="checkbox" checked={shift.include} onChange={(e) => updateShift(i, { include: e.target.checked })} />{shift.name || "משמרת חדשה"}</label>
        {shift.existing && <><p>קיים: {String(shift.existing.start_time || "")}–{String(shift.existing.end_time || "")} · תקן כללי: {String((shift.existing.staffing as { days?: string[]; headcount?: number }[] | undefined)?.find((s) => !s.days?.length)?.headcount ?? shift.existing.headcount ?? 1)}</p>
          <label className="manual-check"><input type="checkbox" checked={shift.replace} onChange={(e) => updateShift(i, { replace: e.target.checked })} />עדכון שעות והתקן הכללי לפי הטיוטה</label></>}
        <div className="manual-grid three">
          <Field label="שם המשמרת"><input value={shift.name} readOnly={!!shift.existing} maxLength={200} onChange={(e) => updateShift(i, { name: e.target.value })} /></Field>
          <Field label="התחלה"><TimeInput value={shift.start_time} onChange={(value) => updateShift(i, { start_time: value })} /></Field>
          <Field label="סיום"><TimeInput value={shift.end_time} onChange={(value) => updateShift(i, { end_time: value })} /></Field>
          <Field label="תקן כללי"><input type="number" min={0} max={100} value={Number.isFinite(shift.headcount) ? shift.headcount : ""} onChange={(e) => updateShift(i, { headcount: e.target.value === "" ? NaN : Number(e.target.value) })} /></Field>
        </div>
        <small>{shift.hours_source === "file" ? "שעות מהקובץ" : "שעות שהושלמו כברירת מחדל"} · {shift.counts.length ? `כמויות שנצפו: ${shift.counts.join(", ")}` : "תקן מוצע: 1, לא זוהה דפוס"}</small>
      </div>)}
      <button type="button" className="ghost-button" onClick={() => setDraft({ ...draft, shifts: [...draft.shifts, { name: "", start_time: "08:00", end_time: "16:00", headcount: 1, include: true, replace: false, sources: [], counts: [], existing: null, hours_source: "default" }] })}>הוספת משמרת</button>
      {invalid && <p role="alert">יש להשלים שעות תקינות ותקן בין 0 ל־100.</p>}
    </>}
    {draft && step === 4 && <>
      <h3>מוכנים להעברה להגדרת היחידה</h3>
      <p>{new Set(people.map((p) => p.target.trim())).size} חיילים: {people.map((p) => p.target).join(", ") || "ללא חיילים נוספים"}</p>
      <ul>{shifts.map((s, i) => <li key={i}>{s.name}: {s.existing && !s.replace ? "שמירת ההגדרה הקיימת" : `${s.start_time}–${s.end_time}, תקן ${s.headcount}`}</li>)}</ul>
      <p>לאחר ההעברה משלימים תפקידים והגדרות בטופס ושומרים שם. השיבוצים שבקובץ לא מיובאים ללוח.</p>
    </>}
    <footer>
      {draft && <button type="button" className="ghost-button" disabled={busy} onClick={() => setDraft(step <= 1 ? null : { ...draft, step: step - 1 })}>{step === 1 ? "בחירת קובץ אחר" : "חזרה"}</button>}
      {draft && step < 4 && <button type="button" className="primary-button" disabled={busy || (step === 3 && invalid)} onClick={() => setDraft({ ...draft, step: step + 1 })}>המשך</button>}
      {draft && step === 4 && <button type="button" className="primary-button" disabled={invalid || (!people.length && !shifts.length)} onClick={() => {
        try { sessionStorage.removeItem(key); } catch { /* Storage is optional. */ }
        onApply(people.map((p) => ({ name: p.target.trim() })), shifts.filter((s) => !s.existing || s.replace).map((s) => ({ name: s.name.trim(), start_time: s.start_time, end_time: s.end_time, headcount: s.headcount })));
        setDraft(null);
      }}>אישור והעברה לטופס ההגדרה</button>}
    </footer>
  </section>;
}
