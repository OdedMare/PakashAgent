"use client";

import { CalendarOff, Clock3, GripVertical, Plus, Trash2, UserRound } from "lucide-react";
import { useMemo, useState } from "react";

import { EMPLOYEE_DRAG_TYPE } from "@/components/Board/dragData";
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
  onAdd,
  onRemove,
}: {
  employees: Record<string, unknown>[];
  shifts: Record<string, unknown>[];
  constraints: Constraint[];
  stats?: ShiftStats;
  dark?: boolean;
  /** A roster drag creates a new assignment; moving an existing card remains separate. */
  draggable?: boolean;
  readOnly?: boolean;
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
}) {
  const [adding, setAdding] = useState(false);
  const names = employees
    .map((row) => text(row.name))
    .filter((name) => name !== "");
  const shiftNames = shifts
    .map((row) => text(row.name))
    .filter((name) => name !== "");
  const hueOf = useMemo(() => buildPalette(names), [names]);
  const loadByName = useMemo(
    () => new Map((stats?.by_employee ?? []).map((row) => [row.employee, row])),
    [stats?.by_employee],
  );

  return (
    <aside className="team-panel" aria-label="הצוות והאילוצים">
      <section className="panel-section">
        <h3>
          <UserRound size={15} />
          הצוות
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
                  </span>
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
              </li>
            );
          })}
          {names.length === 0 ? (
            <li className="panel-empty">אין עובדים בפרופיל עדיין.</li>
          ) : null}
        </ul>
      </section>

      <section className="panel-section">
        <h3>
          <CalendarOff size={15} />
          אילוצים
          <span className="panel-count">{constraints.length}</span>
        </h3>

        <ul className="constraints">
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
          {constraints.length === 0 ? (
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
                onAdd(input);
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

  const ready =
    employee.trim() !== "" &&
    date !== "" &&
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
        <span>תאריך</span>
        <input
          type="date"
          value={date}
          onChange={(event) => setDate(event.target.value)}
          required
        />
      </label>

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

function formatWindow(row: Constraint): string {
  if (row.start_time && row.end_time) return `${row.start_time}–${row.end_time}`;
  if (row.start_time) return `החל מ־${row.start_time}`;
  if (row.end_time) return `עד ${row.end_time}`;
  return "";
}

function text(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}
