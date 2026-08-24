"use client";

import { CalendarOff, Clock3, GripVertical, Pencil, Plus, Repeat2, Trash2, UserRound } from "lucide-react";
import { useMemo, useState } from "react";

import { EMPLOYEE_DRAG_TYPE } from "@/components/Board/dragData";
import { DateInput } from "@/components/DateInput";
import type { Constraint, ShiftStats } from "@/types";

import { formatDate } from "./Calendar";
import { buildPalette, colorStyle } from "./palette";

/** The roster and the constraints recorded against it.
 *
 *  **Employees do not enter these themselves.** They have no account at all
 *  ([D10](../../../docs/DECISIONS.md#d10--one-workspace-per-team-the-boss-holds-a-password-members-hold-a-link))
 *  and they never write ([D5](../../../docs/DECISIONS.md#d5--employees-are-read-only)),
 *  so what `source` records is where the information *came from*, not who
 *  typed it: the manager entering something, the agent picking it up in
 *  conversation, or the manager writing down what an employee told them out
 *  of band. Labelling that honestly matters — "דנה מסרה" and "המנהל קבע" are
 *  different facts, and flattening them would make the roster look like it
 *  holds employee submissions it does not. */
export function TeamPanel({
  employees,
  shifts,
  constraints,
  stats,
  dark = false,
  draggable = false,
  readOnly = false,
  rotationMode = "round",
  onAdd,
  onRemove,
  onSaveProfile,
}: {
  employees: Record<string, unknown>[];
  shifts: Record<string, unknown>[];
  constraints: Constraint[];
  stats?: ShiftStats;
  dark?: boolean;
  /** A roster drag creates a new assignment; moving an existing card remains separate. */
  draggable?: boolean;
  readOnly?: boolean;
  rotationMode?: "round" | "triplet";
  onAdd?: (input: {
    employee: string;
    constraint_date: string;
    shift_name?: string;
    available?: boolean;
    start_time?: string;
    end_time?: string;
    is_hard?: boolean;
    reason?: string;
    source?: string;
  }) => void;
  onRemove?: (rowId: string) => void;
  onSaveProfile?: (input: {
    employees?: Record<string, unknown>[];
    shifts?: Record<string, unknown>[];
  }) => void;
}) {
  const [adding, setAdding] = useState(false);
  const [editingEmployee, setEditingEmployee] = useState<string | null>(null);
  const [addingEmployee, setAddingEmployee] = useState(false);
  const [editingShift, setEditingShift] = useState<string | null>(null);
  const [addingShift, setAddingShift] = useState(false);
  const names = employees
    .map((row) => text(row.name))
    .filter((name) => name !== "");
  const shiftNames = shifts
    .map((row) => text(row.name))
    .filter((name) => name !== "");
  const recurringConstraints = employees.flatMap((person) =>
    (Array.isArray(person.recurring_constraints) ? person.recurring_constraints : [])
      .map((rule, index) => ({ employee: text(person.name), rule: record(rule), index })),
  );
  const hueOf = useMemo(() => buildPalette(names), [names]);
  const loadByName = useMemo(
    () => new Map((stats?.by_employee ?? []).map((row) => [row.employee, row])),
    [stats?.by_employee],
  );

  return (
    <aside className="team-panel" aria-label="כוח האדם, התקינה והאילוצים">
      <section className="panel-section">
        <h3>
          <UserRound size={15} />
          כוח אדם
          <span className="panel-count">{names.length}</span>
        </h3>
        {draggable && names.length ? (
          <p className="roster-help">
            גררו עובד או עובדת אל משמרת פנויה בלוח.
          </p>
        ) : null}
        <ul className="roster">
          {names.map((name) => {
            const person = employees.find((row) => text(row.name) === name);
            const blocked = constraints.filter(
              (row) =>
                row.employee === name &&
                row.is_hard &&
                (!row.available || Boolean(row.start_time || row.end_time)),
            ).length;
            const load = loadByName.get(name);
            return (
              <li
                key={name}
                className={`roster-card${draggable ? " is-draggable" : ""}`}
                draggable={draggable}
                onDragStart={(event) => {
                  if (!draggable) return;
                  event.dataTransfer.setData(EMPLOYEE_DRAG_TYPE, name);
                  event.dataTransfer.setData("text/plain", name);
                  event.dataTransfer.effectAllowed = "copy";
                }}
                title={draggable ? `גרירת ${name} למשמרת` : undefined}
              >
                <span
                  className="roster-avatar"
                  style={colorStyle(hueOf(name), dark)}
                  aria-hidden="true"
                >
                  {name.slice(0, 1)}
                </span>
                <span className="roster-person">
                  <span className="roster-name">{name}</span>
                  <span className="roster-role">
                    {text(person?.role) || "ללא תפקיד מוגדר"}
                    {person ? ` · ${exitPatternLabel(person)}` : ""}
                    {text(person?.rotation_group) ? ` ${text(person?.rotation_group)}` : ""}
                    {text(person?.service_type) ? ` · ${SERVICE_TYPE_LABELS[text(person?.service_type)] ?? text(person?.service_type)}` : ""}
                  </span>
                  {person?.is_shift_manager ? <span className="roster-capability">מפקד/ת משמרת</span> : null}
                  {person?.can_train ? <span className="roster-capability">מוסמך/ת לחפוף</span> : null}
                  {text(person?.notes) ? <span className="roster-note">{text(person?.notes)}</span> : null}
                </span>
                <span className="roster-load" aria-label="עומס בסידור הנוכחי">
                  <span title="מספר משמרות">{load?.shifts ?? 0} משמרות</span>
                  <span title="מספר שעות">
                    <Clock3 size={11} /> {formatHours(load?.hours ?? 0)}
                  </span>
                  {blocked ? (
                    <span className="roster-blocked" title="אילוצים רשומים">
                      <CalendarOff size={12} /> {blocked}
                    </span>
                  ) : null}
                </span>
                {draggable ? (
                  <GripVertical className="roster-grip" size={17} aria-hidden="true" />
                ) : null}
                {onSaveProfile ? (
                  <button
                    type="button"
                    className="icon-button subtle"
                    onClick={() => {
                      setAddingEmployee(false);
                      setEditingEmployee(name);
                    }}
                    aria-label={`עריכת ${name}`}
                  >
                    <Pencil size={13} />
                  </button>
                ) : null}
              </li>
            );
          })}
          {names.length === 0 ? (
            <li className="panel-empty">אין עובדים בפרופיל עדיין.</li>
          ) : null}
        </ul>
        {onSaveProfile ? (
          addingEmployee || editingEmployee ? (
            <EmployeeForm
              initial={editingEmployee
                ? employees.find((row) => text(row.name) === editingEmployee)
                : undefined}
              shiftNames={shiftNames}
              defaultExitPattern={rotationMode}
              onCancel={() => {
                setAddingEmployee(false);
                setEditingEmployee(null);
              }}
              onSubmit={(employee) => {
                const next = editingEmployee
                  ? employees.map((row) => text(row.name) === editingEmployee
                    ? { ...row, ...employee }
                    : row)
                  : [...employees, employee];
                onSaveProfile({ employees: next });
                setAddingEmployee(false);
                setEditingEmployee(null);
              }}
            />
          ) : (
            <button
              type="button"
              className="ghost-button full"
              onClick={() => setAddingEmployee(true)}
            >
              <Plus size={14} />
              הוספת עובד/ת
            </button>
          )
        ) : null}
      </section>

      <section className="panel-section">
        <h3>
          <Clock3 size={15} />
          סוגי משמרות
          <span className="panel-count">{shiftNames.length}</span>
        </h3>
        <ul className="roster shift-types">
          {shifts.map((shift) => {
            const name = text(shift.name);
            if (!name) return null;
            return (
              <li className="roster-card shift-card" key={name}>
                <span className="roster-person">
                  <span className="roster-name">{name}</span>
                  <span className="roster-role">
                    {text(shift.start_time) || "—"}–{text(shift.end_time) || "—"}
                    {` · ${SHIFT_TYPE_LABELS[text(shift.shift_type)] ?? (Boolean(shift.is_on_call) ? "כוננות" : "רגילה")}`}
                    {shift.requires_shift_manager ? " · נדרש מפקד/ת" : ""}
                  </span>
                </span>
                <span className="roster-load">תקן {shiftHeadcount(shift)}</span>
                {onSaveProfile ? (
                  <button
                    type="button"
                    className="icon-button subtle"
                    onClick={() => {
                      setAddingShift(false);
                      setEditingShift(name);
                    }}
                    aria-label={`עריכת משמרת ${name}`}
                  >
                    <Pencil size={13} />
                  </button>
                ) : null}
              </li>
            );
          })}
        </ul>
        {onSaveProfile ? (
          addingShift || editingShift ? (
            <ShiftForm
              initial={editingShift
                ? shifts.find((row) => text(row.name) === editingShift)
                : undefined}
              onCancel={() => {
                setAddingShift(false);
                setEditingShift(null);
              }}
              onSubmit={(shift) => {
                const next = editingShift
                  ? shifts.map((row) => text(row.name) === editingShift
                    ? { ...row, ...shift }
                    : row)
                  : [...shifts, shift];
                onSaveProfile({ shifts: next });
                setAddingShift(false);
                setEditingShift(null);
              }}
            />
          ) : (
            <button
              type="button"
              className="ghost-button full"
              onClick={() => setAddingShift(true)}
            >
              <Plus size={14} />
              הוספת סוג משמרת
            </button>
          )
        ) : null}
        <p className="roster-help">
          שינוי סוג משמרת משפיע על סידורים חדשים; לוחות קיימים נשמרים כפי שנבנו.
        </p>
      </section>

      <section className="panel-section">
        <h3>
          <CalendarOff size={15} />
          אילוצים
          <span className="panel-count">{constraints.length + recurringConstraints.length}</span>
        </h3>

        <ul className="constraints">
          {recurringConstraints.map(({ employee, rule, index }) => (
            <li key={`recurring-${employee}-${index}`}>
              <Repeat2 size={14} aria-hidden="true" />
              <div className="constraint-main">
                <span className="constraint-who">{employee}</span>
                <span className="constraint-when">
                  קבוע · {strings(rule.days).length ? strings(rule.days).join(", ") : "כל יום"}
                  {strings(rule.shifts).length ? ` · ${strings(rule.shifts).join(", ")}` : " · כל המשמרות"}
                </span>
              </div>
              {text(rule.reason) ? <span className="constraint-reason">{text(rule.reason)}</span> : null}
              <span className="constraint-source">{rule.is_hard === false ? "העדפה" : "קשיח"}</span>
              {!readOnly && onSaveProfile ? (
                <button type="button" className="icon-button subtle" aria-label={`מחיקת האילוץ הקבוע של ${employee}`} onClick={() => {
                  const next = employees.map((person) => {
                    if (text(person.name) !== employee) return person;
                    const recurring = Array.isArray(person.recurring_constraints) ? person.recurring_constraints : [];
                    return { ...person, recurring_constraints: recurring.filter((_, ruleIndex) => ruleIndex !== index) };
                  });
                  onSaveProfile({ employees: next });
                }}><Trash2 size={14} /></button>
              ) : null}
            </li>
          ))}
          {constraints.map((row) => (
            <li key={row.id}>
              <div className="constraint-main">
                <span className="constraint-who">{row.employee}</span>
                <span className="constraint-when">
                  {formatDate(row.constraint_date)}
                  {row.shift_name ? ` · ${row.shift_name}` : " · כל היום"}
                  {formatWindow(row) ? ` · ${formatWindow(row)}` : ""}
                </span>
              </div>
              {row.reason ? (
                <span className="constraint-reason">{row.reason}</span>
              ) : null}
              <span className={`constraint-source source-${row.source}`}>
                {SOURCE_LABELS[row.source] ?? row.source}
              </span>
              <span className="constraint-source">
                {row.is_hard ? "קשיח" : "העדפה"}
              </span>
              {!readOnly && onRemove ? (
                <button
                  type="button"
                  className="icon-button subtle"
                  onClick={() => onRemove(row.id)}
                  aria-label={`מחיקת האילוץ של ${row.employee}`}
                >
                  <Trash2 size={14} />
                </button>
              ) : null}
            </li>
          ))}
          {constraints.length === 0 && recurringConstraints.length === 0 ? (
            <li className="panel-empty">
              לא נרשמו אילוצים לתקופה הזו.
            </li>
          ) : null}
        </ul>

        {!readOnly && onAdd ? (
          adding ? (
            <ConstraintForm
              names={names}
              shiftNames={shiftNames}
              onCancel={() => setAdding(false)}
              onSubmit={(input) => {
                if (input.duration === "permanent" && onSaveProfile) {
                  const next = employees.map((person) => {
                    if (text(person.name) !== input.employee) return person;
                    const recurring = Array.isArray(person.recurring_constraints) ? person.recurring_constraints : [];
                    return {
                      ...person,
                      recurring_constraints: [...recurring, {
                        days: input.weekdays,
                        shifts: input.shift_name ? [input.shift_name] : [],
                        available: input.available,
                        start_time: input.start_time,
                        end_time: input.end_time,
                        is_hard: input.is_hard,
                        reason: input.reason,
                        source: "manager",
                      }],
                    };
                  });
                  onSaveProfile({ employees: next });
                } else {
                  const { duration: _duration, weekdays: _weekdays, ...temporary } = input;
                  onAdd?.(temporary);
                }
                setAdding(false);
              }}
            />
          ) : (
            <button
              type="button"
              className="ghost-button full"
              onClick={() => setAdding(true)}
            >
              <Plus size={14} />
              רישום אילוץ
            </button>
          )
        ) : null}
      </section>
    </aside>
  );
}

function EmployeeForm({
  initial,
  shiftNames,
  defaultExitPattern,
  onCancel,
  onSubmit,
}: {
  initial?: Record<string, unknown>;
  shiftNames: string[];
  defaultExitPattern: "round" | "triplet";
  onCancel: () => void;
  onSubmit: (employee: Record<string, unknown>) => void;
}) {
  const [name, setName] = useState(text(initial?.name));
  const [role, setRole] = useState(text(initial?.role));
  const [exitPattern, setExitPattern] = useState(
    text(initial?.exit_pattern) || defaultExitPattern,
  );
  const groups = exitPattern === "triplet" ? ["א", "ב", "ג"] : exitPattern === "round" ? ["א", "ב"] : [];
  const [rotationGroup, setRotationGroup] = useState(text(initial?.rotation_group) || groups[0] || "");
  const [serviceType, setServiceType] = useState(text(initial?.service_type) || "standard");
  const [countsTowardStaffing, setCountsTowardStaffing] = useState(initial?.counts_toward_staffing !== false);
  const [isShiftManager, setIsShiftManager] = useState(Boolean(initial?.is_shift_manager));
  const [canTrain, setCanTrain] = useState(Boolean(initial?.can_train));
  const [notes, setNotes] = useState(rawText(initial?.notes));
  const initialEligible = Array.isArray(initial?.eligible_shifts)
    ? initial.eligible_shifts.filter((value): value is string => typeof value === "string")
    : shiftNames;
  const [eligible, setEligible] = useState<string[]>(initialEligible);

  return (
    <form className="constraint-form profile-form" onSubmit={(event) => {
      event.preventDefault();
      if (!name.trim()) return;
      onSubmit({ name: name.trim(), role: role.trim(), eligible_shifts: eligible, exit_pattern: exitPattern, rotation_group: rotationGroup, service_type: serviceType, counts_toward_staffing: countsTowardStaffing, is_shift_manager: isShiftManager, can_train: canTrain, notes: notes.trim() });
    }}>
      <label>
        <span>שם *</span>
        <input value={name} maxLength={120} onChange={(event) => setName(event.target.value)} required readOnly={Boolean(initial)} title={initial ? "שם קיים הוא מזהה קבוע" : undefined} />
        {initial ? <small>השם מקושר לזהות ולשיבוצים ולכן נשאר קבוע.</small> : null}
      </label>
      <label>
        <span>תפקיד</span>
        <input value={role} maxLength={120} onChange={(event) => setRole(event.target.value)} />
      </label>
      <div className="constraint-time-grid">
        <label><span>מבנה יציאות</span><select value={exitPattern} onChange={(event) => {
          const pattern = event.target.value;
          setExitPattern(pattern);
          setRotationGroup(pattern === "triplet" || pattern === "round" ? "א" : "");
        }}>{Object.entries(EXIT_PATTERN_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        {groups.length ? <label><span>קבוצה</span><select value={rotationGroup} onChange={(event) => setRotationGroup(event.target.value)}>{groups.map((group) => <option key={group}>{group}</option>)}</select></label> : null}
        <label><span>מעמד</span><select value={serviceType} onChange={(event) => {
          setServiceType(event.target.value);
          if (event.target.value === "overlap") setCountsTowardStaffing(false);
        }}><option value="standard">תקן</option><option value="overlap">נחפף/ת</option><option value="reserve">מילואים</option></select></label>
      </div>
      <label className="profile-check"><input type="checkbox" checked={countsTowardStaffing} onChange={(event) => setCountsTowardStaffing(event.target.checked)} /><span>נספר/ת בתקן</span></label>
      <label className="profile-check"><input type="checkbox" checked={isShiftManager} onChange={(event) => setIsShiftManager(event.target.checked)} /><span>מוסמך/ת כמפקד/ת משמרת</span></label>
      <label className="profile-check"><input type="checkbox" checked={canTrain} onChange={(event) => setCanTrain(event.target.checked)} /><span>מוסמך/ת לחפוף</span></label>
      <label><span>הערות לחייל/ת</span><textarea value={notes} maxLength={200} rows={3} onChange={(event) => setNotes(event.target.value)} placeholder="מידע קבוע שכדאי לקחת בחשבון בשיבוץ" /></label>
      {shiftNames.length ? (
        <fieldset className="profile-checkboxes">
          <legend>משמרות שהעובד/ת יכול/ה לבצע</legend>
          {shiftNames.map((shift) => (
            <label key={shift}>
              <input
                type="checkbox"
                checked={eligible.includes(shift)}
                onChange={(event) => setEligible(event.target.checked
                  ? [...eligible, shift]
                  : eligible.filter((name_) => name_ !== shift))}
              />
              <span>{shift}</span>
            </label>
          ))}
        </fieldset>
      ) : null}
      <FormActions onCancel={onCancel} ready={Boolean(name.trim())} />
    </form>
  );
}

function ShiftForm({
  initial,
  onCancel,
  onSubmit,
}: {
  initial?: Record<string, unknown>;
  onCancel: () => void;
  onSubmit: (shift: Record<string, unknown>) => void;
}) {
  const [name, setName] = useState(text(initial?.name));
  const [start, setStart] = useState(text(initial?.start_time));
  const [end, setEnd] = useState(text(initial?.end_time));
  const [headcount, setHeadcount] = useState(shiftHeadcount(initial));
  const [onCall, setOnCall] = useState(Boolean(initial?.is_on_call));
  const [shiftType, setShiftType] = useState(text(initial?.shift_type) || (onCall ? "on_call" : "regular"));
  const [purpose, setPurpose] = useState(text(initial?.purpose));
  const [requiresManager, setRequiresManager] = useState(Boolean(initial?.requires_shift_manager));

  return (
    <form className="constraint-form profile-form" onSubmit={(event) => {
      event.preventDefault();
      if (!name.trim()) return;
      onSubmit({
        name: name.trim(), start_time: start, end_time: end,
        headcount, shift_type: shiftType, is_on_call: shiftType === "on_call", purpose,
        requires_shift_manager: requiresManager,
      });
    }}>
      <label>
        <span>שם המשמרת *</span>
        <input value={name} maxLength={120} onChange={(event) => setName(event.target.value)} required readOnly={Boolean(initial)} title={initial ? "שם קיים הוא מזהה קבוע" : undefined} />
        {initial ? <small>השם מקושר ללוחות קיימים ולכן נשאר קבוע.</small> : null}
      </label>
      <fieldset className="profile-time-card">
        <legend>שעות המשמרת</legend>
        <div className="constraint-time-grid">
          <label><span>שעת התחלה</span><input type="time" step={300} value={start} onChange={(event) => setStart(event.target.value)} /></label>
          <label><span>שעת סיום</span><input type="time" step={300} value={end} onChange={(event) => setEnd(event.target.value)} /></label>
        </div>
        <small>אפשר להקליד שעה ישירות. סיום מוקדם מההתחלה מסמן משמרת שחוצה חצות.</small>
      </fieldset>
      <label><span>סוג משמרת</span><select value={shiftType} onChange={(event) => { setShiftType(event.target.value); setOnCall(event.target.value === "on_call"); }}><option value="regular">רגילה</option><option value="overlap">חפיפה</option><option value="on_call">כוננות</option></select></label>
      <label><span>ייעוד</span><input value={purpose} maxLength={120} onChange={(event) => setPurpose(event.target.value)} placeholder="סיור, חמ״ל, חפיפה…" /></label>
      <label><span>תקן בסיסי</span><input type="number" min={1} max={100} value={headcount} onChange={(event) => setHeadcount(Number(event.target.value) || 1)} /></label>
      <label className="profile-check"><input type="checkbox" checked={requiresManager} onChange={(event) => setRequiresManager(event.target.checked)} /><span>נדרש/ת מפקד/ת משמרת מוסמך/ת</span></label>
      <FormActions onCancel={onCancel} ready={Boolean(name.trim())} />
    </form>
  );
}

function FormActions({ onCancel, ready }: { onCancel: () => void; ready: boolean }) {
  return (
    <div className="constraint-form-actions">
      <button type="button" className="ghost-button" onClick={onCancel}>ביטול</button>
      <button type="submit" className="primary-button" disabled={!ready}>שמירה</button>
    </div>
  );
}

function shiftHeadcount(shift?: Record<string, unknown>): number {
  const staffing = Array.isArray(shift?.staffing) ? shift.staffing : [];
  const fallback = staffing.find((group) => {
    if (!group || typeof group !== "object") return false;
    const days = (group as { days?: unknown }).days;
    return !Array.isArray(days) || days.length === 0;
  }) as { headcount?: unknown } | undefined;
  return typeof fallback?.headcount === "number" ? fallback.headcount : 1;
}

function formatHours(hours: number): string {
  return Number.isInteger(hours) ? `${hours} ש׳` : `${hours.toFixed(1)} ש׳`;
}

/** Recording one constraint.
 *
 *  `source` is a real question rather than a hidden default: whether the
 *  manager decided this or an employee reported it is exactly the
 *  distinction the schema keeps, and asking costs one select. */
function ConstraintForm({
  names,
  shiftNames,
  onCancel,
  onSubmit,
}: {
  names: string[];
  shiftNames: string[];
  onCancel: () => void;
  onSubmit: (input: {
    employee: string;
    constraint_date: string;
    shift_name?: string;
    available?: boolean;
    start_time?: string;
    end_time?: string;
    is_hard?: boolean;
    reason?: string;
    source?: string;
    duration: "temporary" | "permanent";
    weekdays: string[];
  }) => void;
}) {
  const [employee, setEmployee] = useState(names[0] ?? "");
  const [date, setDate] = useState("");
  const [shift, setShift] = useState("");
  const [kind, setKind] = useState<"unavailable" | "window">("unavailable");
  const [startTime, setStartTime] = useState("");
  const [endTime, setEndTime] = useState("");
  const [isHard, setIsHard] = useState(true);
  const [reason, setReason] = useState("");
  const [source, setSource] = useState("manager");
  const [duration, setDuration] = useState<"temporary" | "permanent">("temporary");
  const [weekdays, setWeekdays] = useState<string[]>([]);

  const ready =
    employee.trim() !== "" &&
    (duration === "permanent" ? weekdays.length > 0 : date !== "") &&
    (kind === "unavailable" || startTime !== "" || endTime !== "");

  return (
    <form
      className="constraint-form"
      onSubmit={(event) => {
        event.preventDefault();
        if (!ready) return;
        onSubmit({
          employee: employee.trim(),
          constraint_date: date,
          shift_name: shift,
          available: kind === "window",
          start_time: kind === "window" ? startTime : "",
          end_time: kind === "window" ? endTime : "",
          is_hard: isHard,
          reason: reason.trim(),
          source,
          duration,
          weekdays,
        });
      }}
    >
      <label>
        <span>עובד</span>
        {names.length ? (
          <select
            value={employee}
            onChange={(event) => setEmployee(event.target.value)}
          >
            {names.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        ) : (
          <input
            type="text"
            value={employee}
            onChange={(event) => setEmployee(event.target.value)}
          />
        )}
      </label>

      <label>
        <span>משך האילוץ</span>
        <select value={duration} onChange={(event) => setDuration(event.target.value as "temporary" | "permanent")}>
          <option value="temporary">זמני — לתאריך מסוים</option>
          <option value="permanent">קבוע — חוזר בכל שבוע</option>
        </select>
      </label>

      {duration === "temporary" ? <label>
        <span>תאריך</span>
        <DateInput
          value={date}
          onChange={setDate}
          required
        />
      </label> : <fieldset className="profile-checkboxes"><legend>ימים קבועים</legend>{WEEKDAYS.map((day) => <label key={day}><input type="checkbox" checked={weekdays.includes(day)} onChange={(event) => setWeekdays(event.target.checked ? [...weekdays, day] : weekdays.filter((value) => value !== day))} /><span>{day}</span></label>)}</fieldset>}

      <label>
        <span>משמרת</span>
        <select
          value={shift}
          onChange={(event) => setShift(event.target.value)}
        >
          {/* The empty option is the whole-day constraint, which is the
              interview's own convention and how the audit reads it. */}
          <option value="">כל היום</option>
          {shiftNames.map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </select>
      </label>

      <label>
        <span>סוג זמינות</span>
        <select
          value={kind}
          onChange={(event) =>
            setKind(event.target.value as "unavailable" | "window")
          }
        >
          <option value="unavailable">לא זמין/ה</option>
          <option value="window">זמין/ה רק בחלון שעות</option>
        </select>
      </label>

      {kind === "window" ? (
        <div className="constraint-time-grid">
          <label>
            <span>יכול/ה להתחיל מ־</span>
            <input
              type="time"
              value={startTime}
              onChange={(event) => setStartTime(event.target.value)}
            />
          </label>
          <label>
            <span>חייב/ת לסיים עד</span>
            <input
              type="time"
              value={endTime}
              onChange={(event) => setEndTime(event.target.value)}
            />
          </label>
          <small>אפשר למלא רק אחד מהגבולות. למשל 16:00 בלבד.</small>
        </div>
      ) : null}

      <label>
        <span>עוצמת האילוץ</span>
        <select
          value={isHard ? "hard" : "soft"}
          onChange={(event) => setIsHard(event.target.value === "hard")}
        >
          <option value="hard">קשיח — אין לשבץ בניגוד אליו</option>
          <option value="soft">העדפה — אפשר לחרוג כשצריך</option>
        </select>
      </label>

      <label>
        <span>סיבה</span>
        <input
          type="text"
          value={reason}
          maxLength={200}
          onChange={(event) => setReason(event.target.value)}
          placeholder="מחלה, לימודים, מילואים…"
        />
      </label>

      <label>
        <span>מקור</span>
        <select
          value={source}
          onChange={(event) => setSource(event.target.value)}
        >
          <option value="manager">המנהל קבע</option>
          <option value="employee_reported">העובד מסר</option>
        </select>
      </label>

      <div className="constraint-form-actions">
        <button type="button" className="ghost-button" onClick={onCancel}>
          ביטול
        </button>
        <button type="submit" className="primary-button" disabled={!ready}>
          שמירה
        </button>
      </div>
    </form>
  );
}

/** How each provenance reads to the manager. Deliberately says who supplied
 *  the information, since no employee ever entered it through the app. */
const SOURCE_LABELS: Record<string, string> = {
  manager: "המנהל",
  agent: "הסוכן",
  employee_reported: "העובד מסר",
  interview: "מהראיון",
};

const SERVICE_TYPE_LABELS: Record<string, string> = {
  standard: "תקן",
  overlap: "נחפף/ת",
  reserve: "מילואים",
};

const EXIT_PATTERN_LABELS: Record<string, string> = {
  round: "סבב א / ב",
  triplet: "תלתון א / ב / ג",
  hamshushim: "חמשושים",
  shushim: "שושים",
};

const SHIFT_TYPE_LABELS: Record<string, string> = {
  regular: "רגילה",
  overlap: "חפיפה",
  on_call: "כוננות",
};

const WEEKDAYS = ["ראשון", "שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת"];

function formatWindow(row: Constraint): string {
  if (row.start_time && row.end_time) return `${row.start_time}–${row.end_time}`;
  if (row.start_time) return `החל מ־${row.start_time}`;
  if (row.end_time) return `עד ${row.end_time}`;
  return "";
}

function text(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function rawText(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function exitPatternLabel(person: Record<string, unknown>): string {
  const pattern = text(person.exit_pattern);
  if (EXIT_PATTERN_LABELS[pattern]) return EXIT_PATTERN_LABELS[pattern];
  return text(person.rotation_group) === "ג" ? EXIT_PATTERN_LABELS.triplet : EXIT_PATTERN_LABELS.round;
}

function strings(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string" && Boolean(item.trim()))
    : [];
}

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}
