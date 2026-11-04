"use client";

import { DateInput, displayDate } from "@/components/DateInput";
import type { QualificationStanding } from "@/types";

type Row = Record<string, unknown>;

/** One person's dated qualifications (competence and service type are
 *  `SoldierFields`'). Beside each dated row, the server's standing: until
 *  when it holds, counted from the later of the typed date and the last
 *  shift worked. */
export function PersonStandard({ person, standing, onChange }: { person: Row; standing?: QualificationStanding; onChange: (key: string, value: unknown) => void }) {
  const quals = Array.isArray(person.qualifications) ? person.qualifications as { role: string; last_active: string }[] : [];
  const setQual = (index: number, key: "role" | "last_active", value: string) =>
    onChange("qualifications", quals.map((row, at) => at === index ? { ...row, [key]: value } : row));
  return (
    <div className="manual-row-foot">
      {quals.map((row, index) => (
        <span className="manual-rule" key={index}>
          <input aria-label="כשירות לתפקיד" value={row.role} placeholder="תפקיד" onChange={(e) => setQual(index, "role", e.target.value)} />
          <DateInput aria-label="פעילות אחרונה" value={row.last_active} onChange={(iso) => setQual(index, "last_active", iso)} />
          <button type="button" className="icon-button subtle" aria-label="הסרת כשירות" onClick={() => onChange("qualifications", quals.filter((_, at) => at !== index))}>×</button>
          <QualificationBadge row={row.last_active ? standing?.rows.find((item) => item.role === row.role.trim()) : undefined} />
        </span>
      ))}
      {standing ? <small className="qualification-basis">{standing.last_shift ? `משמרת אחרונה ${displayDate(standing.last_shift)} — מאריכה את הכשירות אוטומטית` : "אין משמרת שבוצעה — הכשירות נספרת מהתאריך שהוזן"}</small> : null}
      <button type="button" className="ghost-button" onClick={() => onChange("qualifications", [...quals, { role: "", last_active: "" }])}>+ כשירות</button>
    </div>
  );
}

/** A shift's role composition: how many of each role sit on it. Stored as
 *  `required_roles` with each role repeated per seat. */
export function ShiftRoles({ shift, roles, onChange }: { shift: Row; roles: string[]; onChange: (staffing: Row[]) => void }) {
  const groups = Array.isArray(shift.staffing) ? shift.staffing as Row[] : [];
  const baseIndex = groups.findIndex((group) => !Array.isArray(group.days) || group.days.length === 0);
  const base = baseIndex >= 0 ? groups[baseIndex] : { days: [], headcount: 1, required_roles: [] };
  const required = Array.isArray(base.required_roles) ? base.required_roles as string[] : [];
  const counts = required.reduce<Record<string, number>>((all, role) => ({ ...all, [role]: (all[role] ?? 0) + 1 }), {});
  const listed = [...new Set([...roles, ...Object.keys(counts)])];
  if (!listed.length) return null;
  const set = (role: string, count: number) => {
    const next = { ...counts, [role]: Math.max(0, count) };
    const seats = Object.entries(next).flatMap(([name, n]) => Array.from({ length: n }, () => name));
    const updated = { ...base, required_roles: seats };
    onChange(baseIndex >= 0 ? groups.map((group, at) => at === baseIndex ? updated : group) : [updated, ...groups]);
  };
  return (
    <fieldset className="manual-checkboxes">
      <legend>הרכב תפקידים במשמרת</legend>
      {listed.map((role) => (
        <label key={role}>
          <span>{role}</span>
          <input type="number" min={0} max={20} style={{ width: "4em" }} value={counts[role] ?? 0} onChange={(e) => set(role, Number(e.target.value) || 0)} />
        </label>
      ))}
    </fieldset>
  );
}

/** One qualification's state in words, coloured like the card. */
function QualificationBadge({ row }: { row?: QualificationStanding["rows"][number] }) {
  if (!row) return null;
  const until = displayDate(row.valid_until);
  const label = {
    valid: `כשיר/ה עד ${until}`,
    expiring: row.days_left === 0 ? "הכשירות פגה היום" : `פגה בעוד ${row.days_left} ימים · ${until}`,
    expired: `לא כשיר/ה · פגה ב-${until}`,
  }[row.status];
  return <span className={`qualification-badge is-${row.status}`} role="status">{label}</span>;
}
