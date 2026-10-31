"use client";

import {
  CalendarOff,
  Clock3,
  GripVertical,
  Pencil,
  Plus,
  Repeat2,
  Trash2,
  Undo2,
  UserMinus,
  UserRound,
} from "lucide-react";
import { useMemo, useState } from "react";

import { EMPLOYEE_DRAG_TYPE } from "@/components/Board/dragData";
import { displayDate } from "@/components/DateInput";
import type { Departure } from "@/services/api";
import type { Constraint, DayCycle, ShiftStats } from "@/types";

import { ConfirmDeparture } from "./ConfirmDeparture";
import { buildPalette, colorStyle } from "./palette";
import {
  SOURCE_LABELS,
  SERVICE_TYPE_LABELS,
  SHIFT_TYPE_LABELS,
  formatWindow,
  text,
  exitPatternLabel,
  strings,
  record,
  formatHours,
  shiftHeadcount,
  weekendHeadcount,
} from "./teamLabels";
import { EmployeeForm, ShiftForm } from "./TeamForms";
import { ConstraintForm } from "./TeamConstraintForm";

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
  dayCycles = [],
  today = "",
  onAdd,
  onRemove,
  onSaveProfile,
  onDeleteShift,
  onPreviewDeparture,
  onDepart,
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
  dayCycles?: DayCycle[];
  today?: string;
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
    constraint_type?: "availability" | "duty";
  }) => void;
  onRemove?: (rowId: string) => void;
  onSaveProfile?: (input: {
    employees?: Record<string, unknown>[];
    shifts?: Record<string, unknown>[];
  }) => void;
  /** Deleting a shift type archives it: stored schedules keep their rows. */
  onDeleteShift?: (name: string) => Promise<void>;
  /** Deleting an employee is a departure: an end date, later shifts vacated. */
  onPreviewDeparture?: (input: { employee: string; effective_date?: string }) => Promise<Departure>;
  onDepart?: (input: { employee: string; effective_date?: string; reason?: string }) => Promise<boolean>;
}) {
  const [adding, setAdding] = useState(false);
  const [departing, setDeparting] = useState<string | null>(null);
  const [departBusy, setDepartBusy] = useState(false);
  const [editingEmployee, setEditingEmployee] = useState<string | null>(null);
  const [addingEmployee, setAddingEmployee] = useState(false);
  const [editingShift, setEditingShift] = useState<string | null>(null);
  const [addingShift, setAddingShift] = useState(false);
  const [deletingShift, setDeletingShift] = useState<string | null>(null);
  const names = employees
    .filter((row) => !row.inactive_from || !today || text(row.inactive_from) > today)
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
  const archived = employees.filter((row) => row.inactive_from && today && text(row.inactive_from) <= today);
  /** Undo a departure. Only the end date goes; vacated shifts stay vacated. */
  const restore = (name: string) => onSaveProfile?.({
    employees: employees.map((row) => {
      if (text(row.name) !== name) return row;
      const { inactive_from: _ended, ...rest } = row;
      return rest;
    }),
  });

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
                    {person ? ` · ${exitPatternLabel(person, dayCycles)}` : ""}
                    {text(person?.rotation_group) ? ` ${text(person?.rotation_group)}` : ""}
                    {text(person?.service_type) ? ` · ${SERVICE_TYPE_LABELS[text(person?.service_type)] ?? text(person?.service_type)}` : ""}
                  </span>
                  {text(person?.inactive_from) ? <span className="roster-note">מסיים/ת · {displayDate(text(person?.inactive_from))}</span> : null}
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
                {onSaveProfile && text(person?.inactive_from) ? (
                  <button
                    type="button"
                    className="icon-button subtle"
                    onClick={() => restore(name)}
                    aria-label={`ביטול סיום העבודה של ${name}`}
                    title="ביטול סיום העבודה"
                  >
                    <Undo2 size={13} />
                  </button>
                ) : onDepart && onPreviewDeparture ? (
                  <button
                    type="button"
                    className="icon-button subtle"
                    onClick={() => setDeparting(name)}
                    aria-label={`הוצאת ${name} מהסגל`}
                    title="הוצאה מהסגל"
                  >
                    <UserMinus size={13} />
                  </button>
                ) : null}
              </li>
            );
          })}
          {names.length === 0 ? (
            <li className="panel-empty">אין עובדים בפרופיל עדיין.</li>
          ) : null}
        </ul>
        {archived.length ? <details className="roster-archive"><summary>עובדים שסיימו את העבודה ({archived.length})</summary>
          <ul>{archived.map((person) => <li key={text(person.name)}><strong>{text(person.name)}</strong>
            <span>סיום עבודה · {displayDate(text(person.inactive_from))}</span>
            {onSaveProfile ? <button type="button" className="ghost-button" onClick={() => restore(text(person.name))}>
              <Undo2 size={13} /> החזרה לסגל
            </button> : null}</li>)}</ul>
        </details> : null}
        {departing && onDepart && onPreviewDeparture ? (
          <ConfirmDeparture
            employee={departing}
            today={today}
            busy={departBusy}
            onPreview={onPreviewDeparture}
            onCancel={() => setDeparting(null)}
            onConfirm={async ({ effective_date, reason }) => {
              setDepartBusy(true);
              const done = await onDepart({ employee: departing, effective_date, reason });
              setDepartBusy(false);
              if (done) {
                setDeparting(null);
                if (editingEmployee === departing) setEditingEmployee(null);
              }
            }}
          />
        ) : null}
        {onSaveProfile ? (
          addingEmployee || editingEmployee ? (
            <EmployeeForm
              initial={editingEmployee
                ? employees.find((row) => text(row.name) === editingEmployee)
                : undefined}
              shiftNames={shiftNames}
              defaultExitPattern={rotationMode}
              dayCycles={dayCycles}
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
                <span className="roster-load">תקן {shiftHeadcount(shift)}{weekendHeadcount(shift) ? ` · סופ״ש ${weekendHeadcount(shift)}` : ""}</span>
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
                {onDeleteShift && shiftNames.length > 1 ? (
                  <button
                    type="button"
                    className="icon-button subtle"
                    onClick={() => {
                      setAddingShift(false);
                      setEditingShift(null);
                      setDeletingShift(name);
                    }}
                    aria-label={`מחיקת סוג המשמרת ${name}`}
                    title="מחיקת סוג משמרת"
                  >
                    <Trash2 size={13} />
                  </button>
                ) : null}
              </li>
            );
          })}
        </ul>
        {deletingShift && onDeleteShift ? (
          <div className="constraint-form profile-form" role="alertdialog" aria-label={`מחיקת סוג המשמרת ${deletingShift}`}>
            <strong>למחוק את סוג המשמרת {deletingShift}?</strong>
            <small>
              סידורים שכבר נבנו נשארים כפי שהם. הבנייה הבאה לא תכלול את המשמרת,
              והיא תוסר מהמשמרות המתאימות ומהאילוצים הקבועים של העובדים.
            </small>
            <div className="constraint-form-actions">
              <button type="button" className="ghost-button" onClick={() => setDeletingShift(null)}>ביטול</button>
              <button
                type="button"
                className="danger-button"
                onClick={async () => {
                  const name = deletingShift;
                  setDeletingShift(null);
                  await onDeleteShift(name);
                }}
              >
                <Trash2 size={13} /> מחיקה
              </button>
            </div>
          </div>
        ) : null}
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
          משמרת חדשה נכנסת גם לטיוטות מהיום והלאה, בלי לשנות את השיבוץ הקיים. שינוי במשמרת קיימת חל על בנייה הבאה.
        </p>
      </section>

      <section className="panel-section">
        <h3>
          <CalendarOff size={15} />
          אילוצים ותורנויות
          <span className="panel-count">{constraints.length + recurringConstraints.length}</span>
        </h3>

        <ul className="constraints">
          {recurringConstraints.map(({ employee, rule, index }) => (
            <li key={`recurring-${employee}-${index}`}>
              <Repeat2 size={14} aria-hidden="true" />
              <div className="constraint-main">
                <span className="constraint-who">{employee}</span>
                <span className="constraint-when">
                  {text(rule.constraint_type) === "duty" ? "תורנות קבועה" : "קבוע"} · {strings(rule.days).length ? strings(rule.days).join(", ") : "כל יום"}
                  {strings(rule.shifts).length ? ` · ${strings(rule.shifts).join(", ")}` : " · כל המשמרות"}
                  {text(rule.constraint_type) === "duty" && (text(rule.start_time) || text(rule.end_time)) ? ` · ${text(rule.start_time)}–${text(rule.end_time)}` : ""}
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
                  {displayDate(row.constraint_date)}
                  {row.constraint_type === "duty"
                    ? " · תורנות חוסמת"
                    : row.shift_name ? ` · ${row.shift_name}` : " · כל היום"}
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
                        constraint_type: input.constraint_type,
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
