"use client";

import {
  AlertTriangle,
  CheckCircle2,
  FileSpreadsheet,
  FileWarning,
  Lightbulb,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import { useMemo, useRef, useState } from "react";

import { DateInput } from "@/components/DateInput";
import { confirmImport, previewImport } from "@/services/api";
import type {
  CandidateRule,
  ImportedConstraint,
  ImportedPeriod,
  ImportPreview,
  ReadAssignment,
} from "@/types";

const MAX_FILE_SIZE = 20 * 1024 * 1024;
const ROWS_PER_PAGE = 50;

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
  const [rowPage, setRowPage] = useState<Record<number, number>>({});
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
      people: new Set(
        preview.periods.flatMap((period) =>
          period.assignments
            .map((row) => row.employee.trim())
            .filter(Boolean),
        ),
      ).size,
      constraints: preview.periods.reduce(
        (sum, period) => sum + period.unavailability.length,
        0,
      ),
    };
  }, [preview]);

  /** Incomplete rows stay visible and block confirmation; nothing inferred
   *  from a file is silently filtered out on the way to persistence. */
  const invalid = useMemo(() => {
    if (!preview) return { assignments: 0, constraints: 0 };
    return preview.periods.reduce(
      (count, period, index) => ({
        assignments:
          count.assignments +
          period.assignments.filter(
            (row) =>
              !row.employee.trim() ||
              !(row.shift || chosenShift[index] || "").trim() ||
              !row.date,
          ).length,
        constraints:
          count.constraints +
          period.unavailability.filter(
            (row) => !row.employee.trim() || !row.date,
          ).length,
      }),
      { assignments: 0, constraints: 0 },
    );
  }, [preview, chosenShift]);

  async function read(selected: File[]) {
    if (!selected.length) return;
    const legacy = selected.find((file) => /\.xls$/i.test(file.name));
    if (legacy) {
      setError(
        `${legacy.name}: פורמט .xls הישן אינו נתמך. שמור אותו כ־.xlsx ונסה שוב.`,
      );
      return;
    }
    const unsupported = selected.find(
      (file) => !/\.(xlsx|xlsm|docx)$/i.test(file.name),
    );
    if (unsupported) {
      setError(`${unsupported.name}: אפשר להעלות קובצי Excel או Word בלבד.`);
      return;
    }
    const tooLarge = selected.find((file) => file.size > MAX_FILE_SIZE);
    if (tooLarge) {
      setError(`${tooLarge.name}: הקובץ גדול מ־20MB.`);
      return;
    }
    setFiles(selected);
    setBusy(true);
    setError("");
    try {
      const found = await previewImport(selected, true);
      setPreview(found);
      setOpenPeriod(0);
      setRowPage({});
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "הקריאה נכשלה");
      setPreview(null);
    } finally {
      setBusy(false);
    }
  }

  async function confirm() {
    if (!preview) return;
    if (invalid.assignments || invalid.constraints) {
      setError("יש להשלים או למחוק את השורות המסומנות לפני השמירה.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      // Every period is stored, with the manager's chosen shift filled in
      // where the file named none. Sent from here rather than re-read on the
      // server, so a correction made on this screen is what lands.
      for (const [index, period] of preview.periods.entries()) {
        const rows = period.assignments
          .map((row: ReadAssignment) => ({
            employee: row.employee.trim(),
            shift: (row.shift || chosenShift[index] || "").trim(),
            date: row.date,
          }));
        if (!rows.length) continue;
        const dates = rows.map((row) => row.date).sort();
        await confirmImport({
          assignments: rows,
          unavailability: period.unavailability.map((row) => ({
            ...row,
            employee: row.employee.trim(),
            shift: row.shift.trim(),
          })),
          starts_on: dates[0],
          ends_on: dates[dates.length - 1],
        });
      }
      onImported();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "השמירה נכשלה");
    } finally {
      setBusy(false);
    }
  }

  function updatePeriod(
    periodIndex: number,
    update: (period: ImportedPeriod) => ImportedPeriod,
  ) {
    setPreview((current) =>
      current
        ? {
            ...current,
            periods: current.periods.map((period, index) =>
              index === periodIndex ? update(period) : period,
            ),
          }
        : current,
    );
  }

  function updateAssignment(
    periodIndex: number,
    rowIndex: number,
    patch: Partial<ReadAssignment>,
  ) {
    updatePeriod(periodIndex, (period) => ({
      ...period,
      assignments: period.assignments.map((row, index) =>
        index === rowIndex ? { ...row, ...patch } : row,
      ),
    }));
  }

  function removeAssignment(periodIndex: number, rowIndex: number) {
    updatePeriod(periodIndex, (period) => ({
      ...period,
      assignments: period.assignments.filter((_row, index) => index !== rowIndex),
    }));
  }

  function updateConstraint(
    periodIndex: number,
    rowIndex: number,
    patch: Partial<ImportedConstraint>,
  ) {
    updatePeriod(periodIndex, (period) => ({
      ...period,
      unavailability: period.unavailability.map((row, index) =>
        index === rowIndex ? { ...row, ...patch } : row,
      ),
    }));
  }

  function removeConstraint(periodIndex: number, rowIndex: number) {
    updatePeriod(periodIndex, (period) => ({
      ...period,
      unavailability: period.unavailability.filter(
        (_row, index) => index !== rowIndex,
      ),
    }));
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
                accept=".xlsx,.xlsm,.docx"
                hidden
                onChange={(event) => {
                  read(Array.from(event.target.files ?? []));
                  event.currentTarget.value = "";
                }}
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
              זוהו <strong>{preview.periods.length}</strong> לוחות:{" "}
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
                const pages = Math.max(
                  1,
                  Math.ceil(period.assignments.length / ROWS_PER_PAGE),
                );
                const page = Math.min(rowPage[index] ?? 0, pages - 1);
                const rowStart = page * ROWS_PER_PAGE;
                const visibleRows = period.assignments.slice(
                  rowStart,
                  rowStart + ROWS_PER_PAGE,
                );
                const shiftOptions = Array.from(
                  new Set([...shiftNames, ...period.shifts]),
                );
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
                        {period.assignments.length} שיבוצים
                        {period.unavailability.length
                          ? ` · ${period.unavailability.length} סימוני אי־זמינות`
                          : ""}
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

                        <section className="import-edit-section">
                          <div className="import-edit-title">
                            <h3>שיבוצים שנקראו</h3>
                            <span>אפשר לתקן כל שדה לפני השמירה</span>
                          </div>
                          <div className="import-edit-head" aria-hidden="true">
                            <span>עובד</span>
                            <span>משמרת</span>
                            <span>תאריך</span>
                            <span />
                          </div>
                          <div className="import-edit-rows">
                            {visibleRows.map((row, pageIndex) => {
                              const rowIndex = rowStart + pageIndex;
                              const shift =
                                row.shift || chosenShift[index] || "";
                              return (
                                <div className="import-edit-row" key={rowIndex}>
                                  <label>
                                    <span>עובד</span>
                                    <input
                                      value={row.employee}
                                      list={`import-people-${index}`}
                                      aria-invalid={!row.employee.trim()}
                                      onChange={(event) =>
                                        updateAssignment(index, rowIndex, {
                                          employee: event.target.value,
                                        })
                                      }
                                    />
                                  </label>
                                  <label>
                                    <span>משמרת</span>
                                    <input
                                      value={shift}
                                      list={`import-shifts-${index}`}
                                      aria-invalid={!shift.trim()}
                                      onChange={(event) =>
                                        updateAssignment(index, rowIndex, {
                                          shift: event.target.value,
                                        })
                                      }
                                    />
                                  </label>
                                  <label>
                                    <span>תאריך</span>
                                    <DateInput
                                      value={row.date}
                                      aria-invalid={!row.date}
                                      onChange={(date) =>
                                        updateAssignment(index, rowIndex, {
                                          date,
                                        })
                                      }
                                    />
                                  </label>
                                  <button
                                    type="button"
                                    className="import-delete"
                                    aria-label={`מחיקת השיבוץ של ${row.employee || "עובד ללא שם"}`}
                                    onClick={() =>
                                      removeAssignment(index, rowIndex)
                                    }
                                  >
                                    <Trash2 size={15} />
                                  </button>
                                </div>
                              );
                            })}
                          </div>
                          <datalist id={`import-people-${index}`}>
                            {period.people.map((name) => (
                              <option key={name} value={name} />
                            ))}
                          </datalist>
                          <datalist id={`import-shifts-${index}`}>
                            {shiftOptions.map((name) => (
                              <option key={name} value={name} />
                            ))}
                          </datalist>
                          {pages > 1 ? (
                            <div className="import-pagination">
                              <button
                                type="button"
                                className="ghost-button"
                                disabled={page === 0}
                                onClick={() =>
                                  setRowPage((current) => ({
                                    ...current,
                                    [index]: page - 1,
                                  }))
                                }
                              >
                                הקודם
                              </button>
                              <span>
                                עמוד {page + 1} מתוך {pages}
                              </span>
                              <button
                                type="button"
                                className="ghost-button"
                                disabled={page === pages - 1}
                                onClick={() =>
                                  setRowPage((current) => ({
                                    ...current,
                                    [index]: page + 1,
                                  }))
                                }
                              >
                                הבא
                              </button>
                            </div>
                          ) : null}
                        </section>

                        {period.unavailability.length ? (
                          <section className="import-edit-section constraint">
                            <div className="import-edit-title">
                              <h3>אי־זמינות שנקראה</h3>
                              <span>שורה ללא עובד חייבת שיוך או מחיקה</span>
                            </div>
                            <div className="import-edit-head" aria-hidden="true">
                              <span>עובד</span>
                              <span>משמרת</span>
                              <span>תאריך</span>
                              <span />
                            </div>
                            <div className="import-edit-rows">
                              {period.unavailability.map((row, rowIndex) => (
                                <div className="import-edit-row" key={rowIndex}>
                                  <label>
                                    <span>עובד</span>
                                    <input
                                      value={row.employee}
                                      list={`import-people-${index}`}
                                      placeholder="בחר או הקלד שם"
                                      aria-invalid={!row.employee.trim()}
                                      onChange={(event) =>
                                        updateConstraint(index, rowIndex, {
                                          employee: event.target.value,
                                        })
                                      }
                                    />
                                  </label>
                                  <label>
                                    <span>משמרת</span>
                                    <input
                                      value={row.shift}
                                      list={`import-shifts-${index}`}
                                      onChange={(event) =>
                                        updateConstraint(index, rowIndex, {
                                          shift: event.target.value,
                                        })
                                      }
                                    />
                                  </label>
                                  <label>
                                    <span>תאריך</span>
                                    <DateInput
                                      value={row.date}
                                      aria-invalid={!row.date}
                                      onChange={(date) =>
                                        updateConstraint(index, rowIndex, {
                                          date,
                                        })
                                      }
                                    />
                                  </label>
                                  <button
                                    type="button"
                                    className="import-delete"
                                    aria-label="מחיקת סימון אי־זמינות"
                                    onClick={() =>
                                      removeConstraint(index, rowIndex)
                                    }
                                  >
                                    <Trash2 size={15} />
                                  </button>
                                </div>
                              ))}
                            </div>
                          </section>
                        ) : null}
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

        {error ? (
          <p className="import-error" role="alert">
            {error}
          </p>
        ) : null}

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
              disabled={
                busy ||
                totals.assignments === 0 ||
                Boolean(invalid.assignments || invalid.constraints)
              }
            >
              <CheckCircle2 size={15} />
              {busy
                ? "שומר…"
                : totals.assignments === 0
                  ? "אין שיבוצים לשמירה"
                : invalid.assignments || invalid.constraints
                  ? `יש להשלים ${invalid.assignments + invalid.constraints} שורות`
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
