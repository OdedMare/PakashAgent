"use client";

import {
  AlertTriangle,
  CheckCircle2,
  FileSpreadsheet,
  FileWarning,
  Lightbulb,
  Upload,
  X,
} from "lucide-react";
import { useMemo, useRef, useState } from "react";

import { confirmImport, previewImport } from "@/services/api";
import type { CandidateRule, ImportPreview, ReadAssignment } from "@/types";

import { formatDate } from "./Calendar";

/** Loading a schedule the workplace already kept.
 *
 *  Two screens, and the split is the decision
 *  ([D7](../../../docs/DECISIONS.md#d7--import-infers-layout-boss-confirms)):
 *  **reading a file writes nothing**, and the manager confirms an
 *  interpretation before anything is stored. The confirm button is the only
 *  thing on this component that persists, which is what makes the
 *  confirmation structural rather than a dialog in front of a write that
 *  already happened.
 *
 *  There is no template and no required format. The importer infers what the
 *  axes mean, so a sheet with shifts down the side, one with people down the
 *  side, and one with nothing but dates and names are all readable. Where it
 *  found no shift names at all it says so and asks here, rather than
 *  inventing a vocabulary the manager never declared
 *  ([D9](../../../docs/DECISIONS.md#d9--shift-vocabulary-is-per-workplace)).
 *
 *  Several files at once because that is the real case: the manager has a
 *  folder of past sheets, and a pattern worth learning is only visible
 *  across them. */
export function ImportSchedule({
  shiftNames,
  onImported,
  onClose,
}: {
  /** The workplace's declared shifts, offered when a sheet named none. */
  shiftNames: string[];
  onImported: () => void;
  onClose: () => void;
}) {
  const [files, setFiles] = useState<File[]>([]);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  // Which period the manager is looking at. A year of sheets is many
  // periods, and showing them all expanded would bury the summary.
  const [openPeriod, setOpenPeriod] = useState(0);
  // A shift chosen here for rows that arrived without one. Keyed by period
  // index; only the `date_only` layout ever needs it.
  const [chosenShift, setChosenShift] = useState<Record<number, string>>({});
  // Which learned rules the manager ticked. Nothing is ticked by default —
  // a candidate becomes a rule by being chosen, never by being proposed.
  const [accepted, setAccepted] = useState<Record<number, boolean>>({});
  const picker = useRef<HTMLInputElement>(null);

  const totals = useMemo(() => {
    if (!preview) return { assignments: 0, people: 0, constraints: 0 };
    return {
      assignments: preview.periods.reduce(
        (sum, period) => sum + period.assignments.length,
        0,
      ),
      people: new Set(preview.periods.flatMap((period) => period.people)).size,
      constraints: preview.periods.reduce(
        (sum, period) => sum + period.unavailability.length,
        0,
      ),
    };
  }, [preview]);

  /** Rows that still have no shift, per period. The confirm button waits on
   *  these: a shiftless assignment has no slot on the grid to sit in. */
  const missingShift = useMemo(() => {
    if (!preview) return [] as number[];
    return preview.periods
      .map((period, index) =>
        period.assignments.some((row) => !row.shift) && !chosenShift[index]
          ? index
          : -1,
      )
      .filter((index) => index >= 0);
  }, [preview, chosenShift]);

  async function read(selected: File[]) {
    if (!selected.length) return;
    setFiles(selected);
    setBusy(true);
    setError("");
    try {
      const found = await previewImport(selected, true);
      setPreview(found);
      setOpenPeriod(0);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "הקריאה נכשלה");
      setPreview(null);
    } finally {
      setBusy(false);
    }
  }

  async function confirm() {
    if (!preview) return;
    setBusy(true);
    setError("");
    try {
      // Every period is stored, with the manager's chosen shift filled in
      // where the file named none. Sent from here rather than re-read on the
      // server, so a correction made on this screen is what lands.
      for (const [index, period] of preview.periods.entries()) {
        const rows = period.assignments
          .map((row: ReadAssignment) => ({
            employee: row.employee,
            shift: row.shift || chosenShift[index] || "",
            date: row.date,
          }))
          .filter((row) => row.employee && row.shift && row.date);
        if (!rows.length) continue;
        await confirmImport({
          assignments: rows,
          unavailability: period.unavailability.filter((row) => row.employee),
          starts_on: period.starts_on,
          ends_on: period.ends_on,
        });
      }
      onImported();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "השמירה נכשלה");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop" role="presentation" onClick={onClose}>
      <div
        className="modal import-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="import-title"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="modal-header">
          <h2 id="import-title">
            <FileSpreadsheet size={17} />
            טעינת סידור קיים
          </h2>
          <button
            type="button"
            className="icon-button"
            onClick={onClose}
            aria-label="סגירה"
          >
            <X size={17} />
          </button>
        </header>

        {!preview ? (
          <>
            {/* Said before the first click, because a manager who has been
                asked for a template by other software will assume there is
                one here too and go looking for it. */}
            <p className="modal-summary">
              העלה את קבצי הסידור שכבר יש לך — אקסל או וורד, כמה שתרצה בבת אחת.
              <strong> אין פורמט קבוע</strong>: הקריאה מזהה לבד את מבנה הקובץ,
              גם אם יש בו רק תאריכים ושמות.
            </p>

            <div
              className="import-drop"
              onDragOver={(event) => event.preventDefault()}
              onDrop={(event) => {
                event.preventDefault();
                read(Array.from(event.dataTransfer.files));
              }}
            >
              <Upload size={22} />
              <p>גרור לכאן קבצים, או</p>
              <button
                type="button"
                className="primary-button"
                onClick={() => picker.current?.click()}
                disabled={busy}
              >
                {busy ? "קורא…" : "בחירת קבצים"}
              </button>
              <input
                ref={picker}
                type="file"
                multiple
                accept=".xlsx,.xls,.docx"
                hidden
                onChange={(event) =>
                  read(Array.from(event.target.files ?? []))
                }
              />
            </div>

            {files.length && busy ? (
              <p className="modal-hint">קורא {files.length} קבצים…</p>
            ) : null}
          </>
        ) : (
          <div className="import-result">
            {/* The one sentence D7 asks for, before any detail. */}
            <p className="import-headline">
              נקראו <strong>{preview.periods.length}</strong> קבצים:{" "}
              <strong>{totals.assignments}</strong> שיבוצים,{" "}
              <strong>{totals.people}</strong> אנשים
              {totals.constraints ? (
                <>
                  , <strong>{totals.constraints}</strong> סימוני אי-זמינות
                </>
              ) : null}
              .
            </p>

            {/* Nothing has been written yet, and that is worth stating
                outright — the screen otherwise looks like a result. */}
            <p className="import-pending">
              <AlertTriangle size={14} />
              עדיין לא נשמר כלום. הכל נשמר רק בלחיצה על האישור למטה.
            </p>

            {preview.failures.length ? (
              <div className="import-failures">
                <FileWarning size={14} />
                <div>
                  {preview.failures.map((failure) => (
                    <p key={failure.filename}>
                      <strong>{failure.filename}</strong> — {failure.error}
                    </p>
                  ))}
                </div>
              </div>
            ) : null}

            <div className="import-periods">
              {preview.periods.map((period, index) => {
                const open = openPeriod === index;
                const needsShift =
                  period.assignments.some((row) => !row.shift);
                return (
                  <div className="import-period" key={period.filename + index}>
                    <button
                      type="button"
                      className="import-period-head"
                      onClick={() => setOpenPeriod(open ? -1 : index)}
                      aria-expanded={open}
                    >
                      <span className="import-period-name">
                        {period.filename || `קובץ ${index + 1}`}
                      </span>
                      <span className="import-period-summary">
                        {period.summary}
                      </span>
                    </button>

                    {open ? (
                      <div className="import-period-body">
                        {/* The inferred layout, named. A misread layout is
                            the one error that makes everything else wrong,
                            so it is shown rather than kept internal. */}
                        <p className="import-layout">
                          מבנה שזוהה:{" "}
                          <strong>{layoutName(period.layout)}</strong>
                          {period.shifts.length ? (
                            <> · משמרות: {period.shifts.join("، ")}</>
                          ) : null}
                        </p>

                        {period.warnings.map((warning) => (
                          <p className="import-warning" key={warning}>
                            <AlertTriangle size={13} />
                            {warning}
                          </p>
                        ))}

                        {/* The file named no shift. Asked rather than
                            guessed: inventing one here would be exactly the
                            hardcoding D9 forbids. */}
                        {needsShift ? (
                          <label className="import-shift-pick">
                            <span>לאיזו משמרת שייכים השיבוצים בקובץ הזה?</span>
                            <select
                              value={chosenShift[index] ?? ""}
                              onChange={(event) =>
                                setChosenShift((current) => ({
                                  ...current,
                                  [index]: event.target.value,
                                }))
                              }
                            >
                              <option value="">בחר משמרת…</option>
                              {shiftNames.map((name) => (
                                <option key={name} value={name}>
                                  {name}
                                </option>
                              ))}
                            </select>
                          </label>
                        ) : null}

                        <div className="import-rows">
                          {period.assignments.slice(0, 40).map((row, n) => (
                            <span className="import-row" key={n}>
                              <strong>{row.employee}</strong>
                              {" · "}
                              {row.shift || chosenShift[index] || "—"}
                              {" · "}
                              {formatDate(row.date)}
                            </span>
                          ))}
                          {period.assignments.length > 40 ? (
                            <span className="import-row import-row-more">
                              ועוד {period.assignments.length - 40}…
                            </span>
                          ) : null}
                        </div>
                      </div>
                    ) : null}
                  </div>
                );
              })}
            </div>

            {/* What the history suggests. Separated from the schedule rows
                because it is a different kind of claim: the rows are what
                the file says, these are inferences from it. */}
            {preview.candidate_rules.length ? (
              <div className="import-rules">
                <h3>
                  <Lightbulb size={15} />
                  מה שנלמד מהקבצים
                </h3>
                <p className="modal-hint">
                  אלה הצעות, לא כללים. סמן את מה שנכון — מה שלא תסמן פשוט
                  לא יישמר.
                </p>
                {preview.candidate_rules.map((rule: CandidateRule, index) => (
                  <label className="import-rule" key={index}>
                    <input
                      type="checkbox"
                      checked={Boolean(accepted[index])}
                      onChange={(event) =>
                        setAccepted((current) => ({
                          ...current,
                          [index]: event.target.checked,
                        }))
                      }
                    />
                    <span className="import-rule-body">
                      <span className="import-rule-text">
                        {rule.text}
                        <span
                          className={`import-rule-kind kind-${rule.kind}`}
                        >
                          {rule.kind === "hard" ? "כלל קשיח" : "העדפה"}
                        </span>
                      </span>
                      {/* The count behind the claim, so the manager approves
                          something they can check rather than trust. */}
                      <span className="import-rule-evidence">
                        {rule.evidence}
                      </span>
                    </span>
                  </label>
                ))}
              </div>
            ) : null}

            {preview.notes.length ? (
              <div className="import-notes">
                {preview.notes.map((note) => (
                  <p key={note}>{note}</p>
                ))}
              </div>
            ) : null}
          </div>
        )}

        {error ? <p className="import-error">{error}</p> : null}

        {preview ? (
          <div className="modal-actions">
            <button
              type="button"
              className="ghost-button"
              onClick={() => {
                setPreview(null);
                setFiles([]);
              }}
            >
              קבצים אחרים
            </button>
            <button
              type="button"
              className="primary-button"
              onClick={confirm}
              disabled={busy || missingShift.length > 0}
            >
              <CheckCircle2 size={15} />
              {busy
                ? "שומר…"
                : missingShift.length
                  ? "בחר משמרת כדי להמשיך"
                  : `שמירת ${totals.assignments} שיבוצים`}
            </button>
          </div>
        ) : null}
      </div>
    </div>
  );
}

/** The inferred layout in the manager's language.
 *
 *  Named rather than shown as `shift_major`: the manager is being asked
 *  whether the reading is right, and they cannot answer that about a word
 *  from the codebase. */
function layoutName(layout: string): string {
  if (layout === "shift_major") return "משמרות בשורות, תאריכים בעמודות";
  if (layout === "person_major") return "אנשים בשורות, תאריך ומשמרת בעמודות";
  if (layout === "date_only") return "תאריכים ואנשים, ללא שמות משמרות";
  return layout;
}
