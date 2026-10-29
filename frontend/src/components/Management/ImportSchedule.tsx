"use client";

import { AlertTriangle, FileSpreadsheet, RefreshCw, Sparkles, Upload, Wand2, X } from "lucide-react";
import { useMemo, useRef, useState } from "react";

import { DateInput, displayDate } from "@/components/DateInput";
import { confirmImport, previewImport } from "@/services/api";
import type { ImportLayout, ImportOptions, ImportPreview, Schedule } from "@/types";

const MAX_FILE_SIZE = 20 * 1024 * 1024;
const ROWS_SHOWN = 80;
const AUTO = "__auto__";
const SKIP = "__skip__";

const SOURCE_LABEL: Record<ImportPreview["layout_source"], string> = {
  detected: "זוהה אוטומטית",
  model: "זוהה בעזרת הסוכן",
  manager: "לפי ההגדרה שלך",
};

/** Loading a schedule the workplace already kept, in whatever shape it has.
 *
 *  **Reading a file writes nothing** (D7): every correction here -- the
 *  layout, who a name means, which heading is which shift -- sends the same
 *  file back to be re-read, and only the confirm button stores. There is no
 *  template: the server finds the layout itself, asks the agent when it is
 *  unsure, and the manager can fix it in a few fields or pick another
 *  reading in one click (D39). */
export function ImportSchedule({ employees, shiftNames, onImported, onClose }: {
  /** The roster, offered for names the file writes differently. */
  employees: string[];
  /** The declared shifts, offered for headings the file names its own way. */
  shiftNames: string[];
  onImported: (schedule: Schedule) => void;
  onClose: () => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [options, setOptions] = useState<ImportOptions>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [target, setTarget] = useState<string>("");
  const [hint, setHint] = useState("");
  const picker = useRef<HTMLInputElement>(null);

  async function read(chosen: File, next: ImportOptions, sameReading = false) {
    setBusy(true);
    setError("");
    try {
      const result = await previewImport(chosen, next);
      // A name or a shift mapped is the same reading of the sheet: it keeps
      // how that reading was found and the other readings on offer.
      setPreview(sameReading && preview ? {
        ...result, layout_source: preview.layout_source, explanation: preview.explanation,
        confidence: preview.confidence, alternatives: preview.alternatives,
      } : result);
      setOptions(next);
      const draft = result.overlaps.find((row) => row.status === "draft");
      setTarget(result.overlaps.length && draft ? draft.id : "");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "קריאת הקובץ נכשלה");
    } finally {
      setBusy(false);
    }
  }

  function choose(chosen: File | undefined) {
    if (!chosen) return;
    if (chosen.size > MAX_FILE_SIZE) {
      setError("הקובץ גדול מדי (עד 20MB)");
      return;
    }
    setFile(chosen);
    setPreview(null);
    void read(chosen, {});
  }

  /** Re-read the same file with one more correction. */
  function reread(change: ImportOptions) {
    if (file) void read(file, { ...options, hint: "", ...change });
  }

  /** Re-read with a name or shift mapped, on the layout already showing --
   *  so mapping a name never sends the sheet back to detection or the agent. */
  function remap(change: ImportOptions) {
    if (file && preview) void read(file, { ...options, hint: "", layout: preview.layout, ...change }, true);
  }

  async function confirm() {
    if (!preview) return;
    setBusy(true);
    setError("");
    try {
      const schedule = await confirmImport({
        assignments: preview.assignments,
        unavailability: preview.unavailability.filter((row) => row.employee),
        schedule_id: target || null,
        filename: preview.filename,
      });
      onImported(schedule);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "השמירה נכשלה");
      setBusy(false);
    }
  }

  const published = preview?.overlaps.filter((row) => row.status !== "draft") ?? [];
  const blocked = Boolean(preview && preview.overlaps.length && !target);

  return (
    <div className="modal-backdrop" role="presentation" onClick={busy ? undefined : onClose}>
      <div className="modal import-dialog" role="dialog" aria-modal="true" aria-labelledby="import-title"
        onClick={(event) => event.stopPropagation()}>
        <header className="modal-header">
          <h2 id="import-title"><FileSpreadsheet size={18} /> ייבוא סידור מקובץ</h2>
          <button type="button" className="icon-button" onClick={onClose} aria-label="סגירה" disabled={busy}>
            <X size={18} />
          </button>
        </header>

        <input ref={picker} type="file" hidden accept=".xlsx,.xlsm,.csv,.tsv,.docx"
          onChange={(event) => { choose(event.target.files?.[0]); event.target.value = ""; }} />

        {!preview ? (
          <button type="button" className="import-drop" disabled={busy}
            onClick={() => picker.current?.click()}
            onDragOver={(event) => event.preventDefault()}
            onDrop={(event) => { event.preventDefault(); choose(event.dataTransfer.files?.[0]); }}>
            <Upload size={22} />
            <strong>{busy ? "קורא את הקובץ…" : "בחר או גרור קובץ Excel, CSV או Word"}</strong>
            <span>כל צורה מתאימה: משמרות בשורות או בעמודות, עובדים בשורות, ימים בלי תאריכים, כמה שבועות בגיליון אחד.</span>
          </button>
        ) : (
          <div className="import-body">
            <section className="import-reading">
              <p className="modal-summary"><strong>{preview.summary}</strong></p>
              <p className="import-explanation">
                <span className={`import-source is-${preview.layout_source}`}>{SOURCE_LABEL[preview.layout_source]}</span>
                {preview.explanation}
                <span className="import-confidence">· התאמה {Math.round(preview.confidence * 100)}%</span>
              </p>
              <div className="import-toolbar">
                <button type="button" className="ghost-button" onClick={() => picker.current?.click()} disabled={busy}>
                  <Upload size={14} /> קובץ אחר
                </button>
                {preview.sheets.length > 1 ? (
                  <label className="import-inline">גיליון
                    <select value={preview.sheet_name} disabled={busy}
                      onChange={(event) => reread({ sheet: event.target.value, layout: null })}>
                      {preview.sheets.map((name) => <option key={name} value={name}>{name}</option>)}
                    </select>
                  </label>
                ) : null}
                {preview.assumed_week ? (
                  <label className="import-inline">השבוע מתחיל ב־
                    <DateInput value={options.week_start || preview.assumed_week}
                      onChange={(value) => remap({ week_start: value })} />
                  </label>
                ) : null}
              </div>
              {preview.alternatives.length ? (
                <div className="import-alternatives" aria-label="קריאות אחרות">
                  <span>לא נכון? קריאות אחרות:</span>
                  {preview.alternatives.map((option, index) => (
                    <button key={index} type="button" className="ghost-button" disabled={busy}
                      onClick={() => reread({ layout: option.layout })}>
                      {option.explanation} ({option.rows})
                    </button>
                  ))}
                </div>
              ) : null}
            </section>

            {preview.warnings.length ? (
              <ul className="import-warnings">
                {preview.warnings.map((warning) => <li key={warning}><AlertTriangle size={14} /> {warning}</li>)}
              </ul>
            ) : null}

            <SheetPreview sheet={preview.sheet} layout={preview.layout} />

            <details className="import-section">
              <summary><Wand2 size={14} /> תיקון המבנה</summary>
              <LayoutEditor key={JSON.stringify(preview.layout)} layout={preview.layout} busy={busy}
                onApply={(layout) => reread({ layout })} />
              <div className="import-hint">
                <label className="modal-field">או תאר את הקובץ במילים, והסוכן יקרא אותו שוב
                  <textarea value={hint} maxLength={500} rows={2} placeholder="למשל: העובדים בעמודה הראשונה, יש שני שבועות אחד מתחת לשני, X פירושו חופש"
                    onChange={(event) => setHint(event.target.value)} />
                </label>
                <button type="button" className="ghost-button" disabled={busy || !hint.trim()}
                  onClick={() => reread({ hint: hint.trim(), layout: null, use_model: true })}>
                  <Sparkles size={14} /> קרא שוב עם הסוכן
                </button>
              </div>
            </details>

            <PeopleTable preview={preview} employees={employees} busy={busy}
              onMap={(name, value) => remap({ names: mapped(options.names, name, value) })} />
            <ShiftTable preview={preview} shiftNames={shiftNames} mapping={options.shifts ?? {}} busy={busy}
              onMap={(name, value) => remap({ shifts: mapped(options.shifts, name, value) })} />
            <RowsPreview preview={preview} />

            {preview.overlaps.length ? (
              <section className="import-section import-overlap">
                <h3>כבר קיים סידור בתאריכים האלה</h3>
                {preview.overlaps.filter((row) => row.status === "draft").map((row) => (
                  <label key={row.id} className="import-choice">
                    <input type="radio" name="import-target" checked={target === row.id}
                      onChange={() => setTarget(row.id)} />
                    למזג לתוך הטיוטה {displayDate(row.starts_on)}–{displayDate(row.ends_on)}: המשמרות שבקובץ יוחלפו בימים שבקובץ, כל השאר יישאר
                  </label>
                ))}
                {published.length ? (
                  <p className="modal-hint">
                    {published.map((row) => `${displayDate(row.starts_on)}–${displayDate(row.ends_on)}`).join(", ")} מפורסם; כדי לייבא לתוכו יש להחזיר אותו לטיוטה, או למחוק אותו.
                  </p>
                ) : null}
              </section>
            ) : null}
          </div>
        )}

        {error ? <p className="import-error" role="alert">{error}</p> : null}

        <footer className="modal-actions">
          <button type="button" className="ghost-button" onClick={onClose} disabled={busy}>ביטול</button>
          {preview ? (
            <button type="button" className="primary-button" onClick={() => void confirm()}
              disabled={busy || !preview.assignments.length || blocked}>
              {busy ? <RefreshCw size={14} className="spin" /> : null}
              {target ? "מיזוג לטיוטה" : "שמירה כסידור חדש"} ({preview.assignments.length} שיבוצים)
            </button>
          ) : null}
        </footer>
      </div>
    </div>
  );
}

/** The options map after one select changed: AUTO drops the entry, SKIP
 *  leaves the name out (""), anything else is the chosen value. */
function mapped(current: Record<string, string> | undefined, name: string, value: string) {
  const next = { ...(current ?? {}) };
  if (value === AUTO) delete next[name];
  else next[name] = value === SKIP ? "" : value;
  return next;
}

function SheetPreview({ sheet, layout }: { sheet: string[][]; layout: ImportLayout }) {
  const across = layout.orientation === "dates_across";
  const isHeader = (row: number, column: number) => (across ? row : column) === layout.header;
  const isShift = (row: number, column: number) =>
    layout.shift_line !== null && (across ? row : column) === layout.shift_line;
  if (!sheet.length) return null;
  return (
    <details className="import-section" open>
      <summary>הקובץ כפי שנקרא</summary>
      <div className="import-sheet" dir="rtl">
        <table>
          <thead><tr><th />{sheet[0].map((_cell, column) => <th key={column}>{column + 1}</th>)}</tr></thead>
          <tbody>
            {sheet.map((row, index) => (
              <tr key={index}>
                <th>{index + 1}</th>
                {row.map((cell, column) => (
                  <td key={column} className={isHeader(index, column) ? "is-header" : isShift(index, column) ? "is-shift" : ""}>
                    {cell}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}

/** The layout as a few fields. Numbers are shown one-based, as Excel does. */
function LayoutEditor({ layout, busy, onApply }: {
  layout: ImportLayout; busy: boolean; onApply: (layout: ImportLayout) => void;
}) {
  const [draft, setDraft] = useState(layout);
  const across = draft.orientation === "dates_across";
  const line = across ? "שורה" : "עמודה";
  const cross = across ? "עמודה" : "שורה";
  const set = (change: Partial<ImportLayout>) => setDraft((previous) => ({ ...previous, ...change }));
  const words = (value: string) => value.split(",").map((word) => word.trim()).filter(Boolean);
  return (
    <div className="import-layout">
      <label className="modal-field">התאריכים רצים
        <select value={draft.orientation} onChange={(event) => set({ orientation: event.target.value as ImportLayout["orientation"] })}>
          <option value="dates_across">לרוחב — בשורה</option>
          <option value="dates_down">לאורך — בעמודה</option>
        </select>
      </label>
      <NumberField label={`${line} התאריכים`} value={draft.header} onChange={(value) => set({ header: value ?? 0 })} />
      <NumberField label={`${line} שמות המשמרות מתחת לתאריכים`} value={draft.shift_line} optional
        onChange={(value) => set({ shift_line: value })} />
      <label className="modal-field">כל {across ? "שורה" : "עמודה"} היא
        <select value={draft.lanes} onChange={(event) => set({ lanes: event.target.value as ImportLayout["lanes"] })}>
          <option value="shifts">משמרת — בתאים שמות עובדים</option>
          <option value="people">עובד — בתאים המשמרת או סימון</option>
          <option value="none">רק מקום — בתאים שמות עובדים</option>
        </select>
      </label>
      <NumberField label={`${cross} השמות (ריק = אוטומטי)`} value={draft.label} optional onChange={(value) => set({ label: value })} />
      <NumberField label={`${across ? "שורת" : "עמודת"} נתונים ראשונה`} value={draft.first_line} optional onChange={(value) => set({ first_line: value })} />
      <NumberField label={`${across ? "שורת" : "עמודת"} נתונים אחרונה`} value={draft.last_line} optional onChange={(value) => set({ last_line: value })} />
      <label className="modal-field">סימנים שפירושם &quot;לא זמין&quot; (מופרדים בפסיק)
        <input value={draft.unavailable.join(", ")} onChange={(event) => set({ unavailable: words(event.target.value) })} />
      </label>
      <label className="modal-field">ערכים להתעלם מהם
        <input value={draft.ignore.join(", ")} onChange={(event) => set({ ignore: words(event.target.value) })} />
      </label>
      <button type="button" className="primary-button" disabled={busy} onClick={() => onApply(draft)}>
        <RefreshCw size={14} /> קרא מחדש לפי המבנה הזה
      </button>
    </div>
  );
}

function NumberField({ label, value, optional = false, onChange }: {
  label: string; value: number | null; optional?: boolean; onChange: (value: number | null) => void;
}) {
  return (
    <label className="modal-field">{label}
      <input type="number" min={1} value={value === null ? "" : value + 1} placeholder={optional ? "—" : undefined}
        onChange={(event) => {
          const number = parseInt(event.target.value, 10);
          onChange(Number.isFinite(number) && number > 0 ? number - 1 : optional ? null : 0);
        }} />
    </label>
  );
}

const STATUS_LABEL: Record<string, string> = {
  exact: "תואם", matched: "זוהה", ambiguous: "לא חד־משמעי", unknown: "לא ברשימה",
  mapped: "מופה", skipped: "לא ייובא",
};

function PeopleTable({ preview, employees, busy, onMap }: {
  preview: ImportPreview; employees: string[]; busy: boolean; onMap: (name: string, value: string) => void;
}) {
  if (!preview.people.length) return null;
  const attention = preview.people.filter((row) => !["exact", "matched"].includes(row.status)).length;
  return (
    <details className="import-section" open={attention > 0}>
      <summary>שמות בקובץ ({preview.people.length}{attention ? `, ${attention} דורשים בדיקה` : ""})</summary>
      <table className="import-table">
        <tbody>
          {preview.people.map((row) => (
            <tr key={row.name}>
              <td>{row.name}</td>
              <td><span className={`import-status is-${row.status}`}>{STATUS_LABEL[row.status]}</span></td>
              <td>{row.count}</td>
              <td>
                <select disabled={busy} aria-label={`למי הכוונה ב־${row.name}`}
                  value={row.status === "skipped" ? SKIP : row.status === "mapped" ? row.employee : AUTO}
                  onChange={(event) => onMap(row.name, event.target.value)}>
                  <option value={AUTO}>{row.employee && ["exact", "matched"].includes(row.status) ? `אוטומטי: ${row.employee}` : "להשאיר כמו בקובץ"}</option>
                  {(row.candidates.length ? row.candidates : employees).concat(
                    row.candidates.length ? employees.filter((name) => !row.candidates.includes(name)) : [],
                  ).map((name) => <option key={name} value={name}>{name}</option>)}
                  <option value={SKIP}>לא לייבא</option>
                </select>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </details>
  );
}

function ShiftTable({ preview, shiftNames, mapping, busy, onMap }: {
  preview: ImportPreview; shiftNames: string[]; mapping: Record<string, string>; busy: boolean;
  onMap: (name: string, value: string) => void;
}) {
  const rows = preview.shifts.filter((row) => row.count || row.name);
  if (!rows.length) return null;
  const attention = rows.filter((row) => !row.declared && row.count).length;
  return (
    <details className="import-section" open={attention > 0}>
      <summary>משמרות בקובץ ({rows.length}{attention ? `, ${attention} לא מוגדרות` : ""})</summary>
      <table className="import-table">
        <tbody>
          {rows.map((row) => (
            <tr key={row.name || "none"}>
              <td>{row.name || "ללא משמרת"}</td>
              <td>{row.count}</td>
              <td>
                <select disabled={busy} aria-label={`איזו משמרת היא ${row.name || "ללא משמרת"}`}
                  value={options(row)} onChange={(event) => onMap(row.name, event.target.value)}>
                  <option value={AUTO}>{row.declared ? `אוטומטי: ${row.shift}` : "להשאיר כמו בקובץ"}</option>
                  {shiftNames.map((name) => <option key={name} value={name}>{name}</option>)}
                  <option value={SKIP}>לא לייבא</option>
                </select>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </details>
  );

  function options(row: ImportPreview["shifts"][number]) {
    if (!(row.name in mapping)) return AUTO;
    return mapping[row.name] ? mapping[row.name] : SKIP;
  }
}

function RowsPreview({ preview }: { preview: ImportPreview }) {
  const rows = useMemo(
    () => [...preview.assignments].sort((a, b) => a.date.localeCompare(b.date) || a.shift.localeCompare(b.shift)),
    [preview.assignments],
  );
  return (
    <details className="import-section">
      <summary>השיבוצים שיישמרו ({rows.length})</summary>
      <table className="import-table">
        <tbody>
          {rows.slice(0, ROWS_SHOWN).map((row, index) => (
            <tr key={index}><td>{displayDate(row.date)}</td><td>{row.shift || "—"}</td><td>{row.employee}</td></tr>
          ))}
        </tbody>
      </table>
      {rows.length > ROWS_SHOWN ? <p className="modal-hint">ועוד {rows.length - ROWS_SHOWN} שיבוצים</p> : null}
    </details>
  );
}
