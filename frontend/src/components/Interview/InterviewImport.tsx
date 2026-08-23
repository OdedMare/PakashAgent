"use client";

import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  FileSpreadsheet,
  RotateCcw,
  Upload,
} from "lucide-react";
import { useMemo, useRef, useState } from "react";

import { previewImport } from "@/services/api";
import type { ImportPreview, InterviewSeed } from "@/types";

const WEEKDAYS = [
  "ראשון",
  "שני",
  "שלישי",
  "רביעי",
  "חמישי",
  "שישי",
  "שבת",
];

export function InterviewImport({
  workplaceName,
  interviewBusy,
  onStart,
  onBack,
}: {
  workplaceName?: string;
  interviewBusy: boolean;
  onStart: (seed: InterviewSeed) => void;
  onBack: () => void;
}) {
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [reading, setReading] = useState(false);
  const [error, setError] = useState("");
  const picker = useRef<HTMLInputElement>(null);
  const seed = useMemo(
    () => (preview ? toSeed(preview, workplaceName) : null),
    [preview, workplaceName],
  );

  async function read(files: File[]) {
    if (!files.length) return;
    setReading(true);
    setError("");
    try {
      setPreview(await previewImport(files, false));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "הקריאה נכשלה");
    } finally {
      setReading(false);
    }
  }

  const people = seed ? Object.keys(seed.employees ?? {}).length : 0;
  const shifts = seed ? Object.keys(seed.shifts ?? {}).length : 0;
  const warnings =
    preview?.periods.reduce(
      (total, period) => total + period.warnings.length,
      preview.failures.length,
    ) ?? 0;

  return (
    <div className="center interview-import-page">
      <section className="interview-import" aria-labelledby="import-first-title">
        <button type="button" className="import-back" onClick={onBack}>
          <ArrowRight size={15} aria-hidden="true" />
          חזרה
        </button>

        <div className="welcome-kicker">
          <span className="brand-mark" aria-hidden="true">
            <FileSpreadsheet size={17} />
          </span>
          <span>למידה מסידור קיים</span>
        </div>

        <h1 id="import-first-title">
          {preview ? "מצאתי נקודת התחלה טובה" : "תנו לסידור הקיים לדבר קודם"}
        </h1>

        {!preview ? (
          <>
            <p>
              העלו אקסל או וורד בכל מבנה. פקש יזהה אנשים, שמות משמרות
              ודפוסים—ואחר כך ישאל רק כדי לאמת ולהשלים.
            </p>
            <div
              className={`interview-import-drop${reading ? " is-reading" : ""}`}
              onDragOver={(event) => event.preventDefault()}
              onDrop={(event) => {
                event.preventDefault();
                void read(Array.from(event.dataTransfer.files));
              }}
            >
              <Upload size={25} aria-hidden="true" />
              <strong>{reading ? "קורא את הקבצים…" : "גררו לכאן קבצים"}</strong>
              <span>או בחרו כמה קבצים יחד · אין תבנית קבועה</span>
              <button
                type="button"
                className="start-button"
                onClick={() => picker.current?.click()}
                disabled={reading}
              >
                בחירת קבצים
              </button>
              <input
                ref={picker}
                type="file"
                multiple
                accept=".xlsx,.xls,.docx"
                hidden
                onChange={(event) =>
                  void read(Array.from(event.target.files ?? []))
                }
              />
            </div>
          </>
        ) : (
          <>
            <p>
              זה עדיין לא פרופיל מאושר. נכניס את הממצאים לטיוטה ונעבור יחד
              על הפרטים שלא ניתן להסיק מהקובץ.
            </p>

            <dl className="import-found-grid">
              <div>
                <dt>עובדים שנמצאו</dt>
                <dd>{people}</dd>
              </div>
              <div>
                <dt>סוגי משמרות</dt>
                <dd>{shifts}</dd>
              </div>
              <div>
                <dt>קבצים שנקראו</dt>
                <dd>{preview.periods.length}</dd>
              </div>
            </dl>

            <div className="import-found-lines">
              <p>
                <CheckCircle2 size={15} aria-hidden="true" />
                השמות שמצאנו יופיעו מיד בטיוטת הראיון.
              </p>
              <p>
                <CheckCircle2 size={15} aria-hidden="true" />
                שעות, תפקידים וכללים יישארו פתוחים עד שתאשרו אותם.
              </p>
              {warnings ? (
                <p className="has-warning">
                  <AlertTriangle size={15} aria-hidden="true" />
                  {warnings} פרטים דורשים תשומת לב במהלך הראיון.
                </p>
              ) : null}
            </div>

            <div className="import-first-actions">
              <button
                type="button"
                className="start-button"
                onClick={() => seed && onStart(seed)}
                disabled={interviewBusy || !seed}
              >
                {interviewBusy ? "מכין את הטיוטה…" : "המשיכו עם מה שמצאתי"}
              </button>
              <button
                type="button"
                className="import-retry"
                onClick={() => setPreview(null)}
                disabled={interviewBusy}
              >
                <RotateCcw size={14} aria-hidden="true" />
                קבצים אחרים
              </button>
            </div>
          </>
        )}

        {error ? <p className="import-first-error" role="alert">{error}</p> : null}
        <p className="import-privacy">
          בשלב הזה הסידור עצמו לא נשמר; רק העובדות שתאשרו בראיון יהפכו
          לפרופיל העבודה.
        </p>
      </section>
    </div>
  );
}

function toSeed(
  preview: ImportPreview,
  workplaceName?: string,
): InterviewSeed {
  const employees: Record<string, Set<string>> = {};
  const shifts: Record<string, Set<string>> = {};

  for (const period of preview.periods) {
    for (const name of period.people) employees[name] ??= new Set();
    for (const name of period.shifts) shifts[name] ??= new Set();
    for (const row of period.assignments) {
      if (!row.employee) continue;
      employees[row.employee] ??= new Set();
      if (!row.shift) continue;
      employees[row.employee].add(row.shift);
      shifts[row.shift] ??= new Set();
      const day = weekday(row.date);
      if (day) shifts[row.shift].add(day);
    }
  }

  const starts = preview.periods.map((period) => period.starts_on).filter(Boolean);
  const ends = preview.periods.map((period) => period.ends_on).filter(Boolean);
  return {
    workplace_name: workplaceName,
    source_files: preview.periods.map((period) => period.filename).filter(Boolean),
    employees: Object.fromEntries(
      Object.entries(employees).map(([name, names]) => [name, [...names]]),
    ),
    shifts: Object.fromEntries(
      Object.entries(shifts).map(([name, days]) => [name, [...days]]),
    ),
    starts_on: starts.sort()[0] ?? "",
    ends_on: ends.sort().at(-1) ?? "",
  };
}

function weekday(value: string): string {
  const date = new Date(`${value}T12:00:00Z`);
  return Number.isNaN(date.getTime()) ? "" : WEEKDAYS[date.getUTCDay()];
}
