"use client";

import { ArrowLeftRight, CalendarPlus, CheckCircle2, UserPlus } from "lucide-react";
import { useState } from "react";

import { ReplacementPanel } from "./ReplacementPanel";
import { EmployeeForm, ShiftForm } from "./TeamPanel";

type Action = "replace" | "soldier" | "shift";

const ACTIONS: { id: Action; label: string; icon: React.ReactNode }[] = [
  { id: "replace", label: "החלפת משמרת", icon: <ArrowLeftRight size={15} /> },
  { id: "soldier", label: "הוספת חייל", icon: <UserPlus size={15} /> },
  { id: "shift", label: "הוספת משמרת", icon: <CalendarPlus size={15} /> },
];

/** The changes tab: the three changes a manager makes to a running board.
 *
 *  Replacing a shift goes to the conversation as a plan, exactly as the
 *  replacement tab always did (D36). Adding a soldier or a shift saves the
 *  profile, and the server fits the newcomer into every draft from today on
 *  while keeping the rows already there (D37); the board on screen shows
 *  that refit as a running build. */
export function ChangesPanel({
  employees,
  activeEmployees,
  shifts,
  today,
  rotationMode = "round",
  disabled,
  onPrepare,
  onSaveProfile,
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
}) {
  const [action, setAction] = useState<Action>("replace");
  const [done, setDone] = useState("");
  const [error, setError] = useState("");
  // A new form after each save, so the next soldier starts from blank fields.
  const [formKey, setFormKey] = useState(0);
  const shiftNames = shifts.map((row) => nameOf(row)).filter(Boolean);

  const choose = (next: Action) => {
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
    if (await onSaveProfile({ [section]: [...rows, added] })) {
      setDone(`${what} «${name}» נוסף/ה ומשולב/ת בסידורי הטיוטה מהיום והלאה, בלי להזיז את השיבוץ הקיים מעבר לנדרש.`);
      setFormKey((key) => key + 1);
    }
  };

  return (
    <section className="changes-panel" aria-labelledby="changes-title">
      <header>
        <h2 id="changes-title">שינויים</h2>
        <p>החלפת משמרת, חייל חדש או משמרת חדשה — הסידור הקיים נשמר ככל האפשר.</p>
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
      {action === "shift" ? (
        <ShiftForm
          key={`shift-${formKey}`}
          onCancel={() => choose("replace")}
          onSubmit={(shift) => void save("shifts", shifts, shift, "המשמרת")}
        />
      ) : null}
    </section>
  );
}

function nameOf(row: Record<string, unknown>): string {
  return typeof row.name === "string" ? row.name.trim() : "";
}
