"use client";

import { Upload } from "lucide-react";
import { useState } from "react";

import { TimeInput } from "@/components/TimeInput";
import { importRoster } from "@/services/api";
import type { GroupStaffing, RosterImportReport, UnitPolicy } from "@/services/api";

import { Field } from "./fields";

/** A reserve unit's roster from its own roster app: the CSV it exports or
 *  the columns it pastes. Each group becomes a day and a night shift with
 *  the composition typed here; people keep their rating, service track and
 *  qualifications. Previewing writes nothing; importing saves the profile. */
export function RosterImport({ unitName, unitPolicy, revision, onImported }: {
  unitName: string;
  unitPolicy: UnitPolicy;
  revision?: number | null;
  onImported: () => void | Promise<void>;
}) {
  const [raw, setRaw] = useState("");
  const [start, setStart] = useState("08:00");
  const [staffing, setStaffing] = useState<GroupStaffing>({ day: {}, night: {} });
  const [report, setReport] = useState<RosterImportReport | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const body = (apply: boolean) => ({
    text: raw, start_time: start, unit_policy: unitPolicy, unit_name: unitName.trim() || undefined,
    staffing: Object.keys(staffing.day).length || Object.keys(staffing.night).length ? staffing : undefined,
    expected_revision: revision ?? undefined, apply,
  });
  const run = async (apply: boolean) => {
    setBusy(true);
    setError("");
    try {
      const result = await importRoster(body(apply));
      setReport(result.report);
      if (!Object.keys(staffing.day).length && !Object.keys(staffing.night).length) {
        const ones = Object.fromEntries(result.report.roles.map((role) => [role, 1]));
        setStaffing({ day: { ...ones }, night: { ...ones } });
      }
      if (apply) await onImported();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "הייבוא נכשל");
    } finally {
      setBusy(false);
    }
  };
  const readFile = async (file: File | undefined) => {
    if (file) setRaw(await file.text());
  };
  const setCount = (part: "day" | "night", role: string, value: string) =>
    setStaffing((current) => ({ ...current, [part]: { ...current[part], [role]: Math.max(0, Number(value) || 0) } }));

  return (
    <div className="manual-list">
      <p className="rotation-derived-note">
        מאפליקציית המשמרות של היחידה: &quot;ייצוא ל-CSV&quot; או העתקת עמודות (שם | טלפון | קבוצה | תפקיד | דירוג | מייל | סוג שירות).
        כל קבוצה הופכת למשמרת יום ולמשמרת לילה משלה, וכל אחד משובץ רק בקבוצת הבית שלו. טלפונים ומיילים לא נשמרים.
      </p>
      <label className="ghost-button"><Upload size={16} /> בחירת קובץ CSV
        <input type="file" accept=".csv,text/csv,text/plain" hidden onChange={(e) => void readFile(e.target.files?.[0])} />
      </label>
      <textarea aria-label="רשימת האנשים" rows={6} value={raw} onChange={(e) => { setRaw(e.target.value); setReport(null); }} placeholder="או הדביקו כאן את התוכן" />
      <div className="manual-grid three">
        <Field label="תחילת משמרת יום (12 שעות)"><TimeInput value={start} onChange={setStart} /></Field>
      </div>
      {report ? (
        <>
          <div className="manual-list compact">
            {report.roles.map((role) => (
              <div className="manual-rule" key={role}>
                <span>{role}</span>
                <Field label="ביום"><input type="number" min={0} max={20} value={staffing.day[role] ?? 0} onChange={(e) => setCount("day", role, e.target.value)} /></Field>
                <Field label="בלילה"><input type="number" min={0} max={20} value={staffing.night[role] ?? 0} onChange={(e) => setCount("night", role, e.target.value)} /></Field>
              </div>
            ))}
          </div>
          <p>
            נקראו {report.read} שורות: {report.added} חדשים, {report.updated} יעודכנו.
            קבוצות: {report.groups.map((group) => `${group.label} (${group.members})`).join(", ") || "—"}.
            משמרות: {report.shifts.join(", ") || "—"}.
          </p>
          {report.errors.length ? (
            <p className="manual-error">{report.errors.slice(0, 8).map((row) => `שורה ${row.line}: ${row.error}`).join(" · ")}</p>
          ) : null}
        </>
      ) : null}
      {error ? <p className="manual-error">{error}</p> : null}
      <div className="manual-header-actions">
        <button type="button" className="ghost-button" disabled={busy || !raw.trim()} onClick={() => void run(false)}>תצוגה מקדימה</button>
        <button type="button" className="primary-button" disabled={busy || !report} onClick={() => void run(true)}>ייבוא ושמירה</button>
      </div>
    </div>
  );
}
