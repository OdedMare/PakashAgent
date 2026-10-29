"use client";

import { ArrowLeftRight, CalendarPlus, CheckCircle2, UserMinus, UserPlus } from "lucide-react";
import { useState } from "react";

import type { Departure } from "@/services/api";

import { ConfirmDeparture } from "./ConfirmDeparture";
import { ReplacementPanel } from "./ReplacementPanel";
import { EmployeeForm, ShiftForm } from "./TeamPanel";

type Action = "replace" | "soldier" | "remove" | "shift";

const ACTIONS: { id: Action; label: string; icon: React.ReactNode }[] = [
  { id: "replace", label: "החלפת משמרת", icon: <ArrowLeftRight size={15} /> },
  { id: "soldier", label: "הוספת חייל", icon: <UserPlus size={15} /> },
  { id: "remove", label: "הוצאת חייל", icon: <UserMinus size={15} /> },
  { id: "shift", label: "הוספת משמרת", icon: <CalendarPlus size={15} /> },
];

/** The changes tab: the four changes a manager makes to a running board.
 *
 *  Replacing a shift goes to the conversation as a plan, exactly as the
 *  replacement tab always did (D36). Adding a soldier or a shift saves the
 *  profile, and the server fits the newcomer into every draft from today on
 *  while keeping the rows already there (D37); the board on screen shows
 *  that refit as a running build. Taking a soldier out is the team panel's
 *  departure: an end date, and every shift from it on vacated, counted in
 *  the dialog before the click. */
export function ChangesPanel({
  employees,
  activeEmployees,
  shifts,
  today,
  rotationMode = "round",
  disabled,
  onPrepare,
  onSaveProfile,
  onPreviewDeparture,
  onDepart,
}: {
  employees: Record<string, unknown>[];
  activeEmployees: string[];
  shifts: Record<string, unknown>[];
  today: string;
  rotationMode?: "round" | "triplet";
  disabled: boolean;
  onPrepare: (message: string) => void;
  onSaveProfile: (input: {
    employees?: Record<string, unknown>[];
    shifts?: Record<string, unknown>[];
  }) => Promise<boolean>;
  onPreviewDeparture: (input: { employee: string; effective_date?: string }) => Promise<Departure>;
  onDepart: (input: { employee: string; effective_date?: string; reason?: string }) => Promise<boolean>;
}) {
  const [action, setAction] = useState<Action>("replace");
  const [done, setDone] = useState("");
  const [error, setError] = useState("");
  // A new form after each save, so the next soldier starts from blank fields.
  const [formKey, setFormKey] = useState(0);
  const shiftNames = shifts.map((row) => nameOf(row)).filter(Boolean);
  // Who may stand a new shift. Everyone by default: a roster that lists
  // each soldier's shifts would otherwise leave the new one with nobody
  // eligible, and the board would show it empty however it was built.
  const [standers, setStanders] = useState<string[]>(activeEmployees);
  const [leaving, setLeaving] = useState("");
  const [departing, setDeparting] = useState(false);
  const [departBusy, setDepartBusy] = useState(false);

  const choose = (next: Action) => {
    if (next === "shift") setStanders(activeEmployees);
    if (next === "remove") setLeaving("");
    setAction(next);
    setDone("");
    setError("");
  };

  const save = async (
    section: "employees" | "shifts",
    rows: Record<string, unknown>[],
    added: Record<string, unknown>,
    what: string,
  ) => {
    const name = nameOf(added);
    if (rows.some((row) => nameOf(row) === name)) {
      setError(`${what} בשם «${name}» כבר קיים/ת`);
      return;
    }
    setError("");
    setDone("");
    const patch = section === "shifts"
      ? { shifts: [...rows, added], employees: withStanders(employees, name, standers, shiftNames) }
      : { [section]: [...rows, added] };
    if (await onSaveProfile(patch)) {
      setDone(`${what} «${name}» נוסף/ה ומשולב/ת בסידורי הטיוטה מהיום והלאה, בלי להזיז את השיבוץ הקיים מעבר לנדרש.`);
      setFormKey((key) => key + 1);
    }
  };

  return (
    <section className="changes-panel" aria-labelledby="changes-title">
      <header>
        <h2 id="changes-title">שינויים</h2>
        <p>החלפת משמרת, חייל חדש, הוצאת חייל או משמרת חדשה — הסידור הקיים נשמר ככל האפשר.</p>
      </header>
      <div className="changes-actions" role="tablist" aria-label="סוג השינוי">
        {ACTIONS.map((item) => (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={action === item.id}
            className={action === item.id ? "is-active" : undefined}
            onClick={() => choose(item.id)}
          >
            {item.icon}
            <span>{item.label}</span>
          </button>
        ))}
      </div>

      {error ? <p className="replacement-error" role="alert">{error}</p> : null}
      {done ? (
        <p className="changes-done" role="status"><CheckCircle2 size={15} /> {done}</p>
      ) : null}

      {action === "replace" ? (
        <ReplacementPanel
          employees={activeEmployees}
          today={today}
          disabled={disabled}
          onPrepare={onPrepare}
        />
      ) : null}
      {action === "soldier" ? (
        <EmployeeForm
          key={`soldier-${formKey}`}
          shiftNames={shiftNames}
          defaultExitPattern={rotationMode}
          onCancel={() => choose("replace")}
          onSubmit={(employee) => void save("employees", employees, employee, "החייל/ת")}
        />
      ) : null}
      {action === "remove" ? (
        <form
          className="changes-remove"
          onSubmit={(event) => {
            event.preventDefault();
            if (!leaving) return;
            setDone("");
            setError("");
            setDeparting(true);
          }}
        >
          <label className="modal-field">
            <span>החייל/ת שיוצא/ת מהסידור</span>
            <select value={leaving} onChange={(event) => setLeaving(event.target.value)} required>
              <option value="">בחירה…</option>
              {activeEmployees.map((person) => (
                <option key={person} value={person}>{person}</option>
              ))}
            </select>
          </label>
          <div className="modal-actions">
            <button type="button" className="ghost-button" onClick={() => choose("replace")}>
              ביטול
            </button>
            <button type="submit" className="danger-button" disabled={disabled || !leaving}>
              <UserMinus size={14} /> הוצאה מהסידור
            </button>
          </div>
        </form>
      ) : null}
      {departing && leaving ? (
        <ConfirmDeparture
          employee={leaving}
          today={today}
          busy={departBusy}
          onPreview={onPreviewDeparture}
          onCancel={() => setDeparting(false)}
          onConfirm={async ({ effective_date, reason }) => {
            setDepartBusy(true);
            const ok = await onDepart({ employee: leaving, effective_date, reason });
            setDepartBusy(false);
            if (ok) {
              setDeparting(false);
              setDone(`«${leaving}» הוצא/ה מהסידור, והמשמרות שלו/ה מהתאריך שנבחר והלאה פונו.`);
              setLeaving("");
            }
          }}
        />
      ) : null}
      {action === "shift" ? (
        <ShiftForm
          key={`shift-${formKey}`}
          onCancel={() => choose("replace")}
          onSubmit={(shift) => void save("shifts", shifts, shift, "המשמרת")}
        >
          {activeEmployees.length ? (
            <fieldset className="profile-checkboxes">
              <legend>מי יכול/ה לבצע את המשמרת</legend>
              {activeEmployees.map((person) => (
                <label key={person}>
                  <input
                    type="checkbox"
                    checked={standers.includes(person)}
                    onChange={(event) => setStanders(event.target.checked
                      ? [...standers, person]
                      : standers.filter((other) => other !== person))}
                  />
                  <span>{person}</span>
                </label>
              ))}
            </fieldset>
          ) : null}
        </ShiftForm>
      ) : null}
    </section>
  );
}

/** The roster with `shift` added to what each chosen soldier may stand.
 *
 *  An empty `eligible_shifts` already means "every shift", so a chosen
 *  soldier with one needs nothing, and an unchosen one is pinned to the
 *  shifts they could stand before — otherwise "every shift" would now
 *  include the new one too. */
function withStanders(
  employees: Record<string, unknown>[],
  shift: string,
  standers: string[],
  previous: string[],
): Record<string, unknown>[] {
  const chosen = new Set(standers);
  return employees.map((row) => {
    const name = nameOf(row);
    const listed = Array.isArray(row.eligible_shifts)
      ? row.eligible_shifts.filter((value): value is string => typeof value === "string")
      : [];
    if (chosen.has(name)) {
      return listed.length && !listed.includes(shift)
        ? { ...row, eligible_shifts: [...listed, shift] }
        : row;
    }
    if (row.inactive_from || listed.length) return row;
    return { ...row, eligible_shifts: previous };
  });
}

function nameOf(row: Record<string, unknown>): string {
  return typeof row.name === "string" ? row.name.trim() : "";
}
