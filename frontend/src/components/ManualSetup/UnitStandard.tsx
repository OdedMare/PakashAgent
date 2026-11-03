"use client";

import type { UnitPolicy } from "@/services/api";

import { Field } from "./fields";

type Row = Record<string, unknown>;

/** The unit's staffing standard: the weak per shift (by competence), how long a
 *  qualification stays valid, shifts per week and fallback roles. */
export function UnitStandard({ policy, roles, onChange }: {
  policy: UnitPolicy;
  roles: string[];
  onChange: (policy: UnitPolicy) => void;
}) {
  const limits = (key: "weekly_shifts" | "weekly_shifts_regular", bound: "min" | "max", value: string) => {
    const current = { ...(policy[key] ?? {}) };
    if (value === "") delete current[bound];
    else current[bound] = Math.max(0, Math.min(14, Number(value) || 0));
    onChange({ ...policy, [key]: current });
  };
  const fallbacks = policy.role_fallbacks ?? {};
  return (
    <>
      <div className="manual-grid three">
        <Field label="מקסימום בכשירות חלשה במשמרת">
          <input type="number" min={0} placeholder="ללא הגבלה" value={policy.max_weak_per_shift ?? ""}
            onChange={(e) => onChange({ ...policy, max_weak_per_shift: e.target.value === "" ? null : Math.max(0, Number(e.target.value) || 0) })} />
        </Field>
        <Field label="תוקף כשירות (ימים)">
          <input type="number" min={1} value={policy.qualification_validity_days ?? 90}
            onChange={(e) => onChange({ ...policy, qualification_validity_days: Math.max(1, Number(e.target.value) || 90) })} />
        </Field>
      </div>
      <div className="manual-grid three">
        <Field label="מילואים · מינ׳ משמרות בשבוע"><input type="number" min={0} value={policy.weekly_shifts?.min ?? ""} onChange={(e) => limits("weekly_shifts", "min", e.target.value)} /></Field>
        <Field label="מילואים · מקס׳ משמרות בשבוע"><input type="number" min={0} value={policy.weekly_shifts?.max ?? ""} onChange={(e) => limits("weekly_shifts", "max", e.target.value)} /></Field>
        <Field label="שאר הסגל · מינ׳ משמרות בשבוע"><input type="number" min={0} value={policy.weekly_shifts_regular?.min ?? ""} onChange={(e) => limits("weekly_shifts_regular", "min", e.target.value)} /></Field>
        <Field label="שאר הסגל · מקס׳ משמרות בשבוע"><input type="number" min={0} value={policy.weekly_shifts_regular?.max ?? ""} onChange={(e) => limits("weekly_shifts_regular", "max", e.target.value)} /></Field>
      </div>
      {roles.length > 1 ? (
        <div className="manual-list compact">
          {roles.map((role) => (
            <div className="manual-rule" key={role}>
              <span>{role} · תפקיד חלופי:</span>
              <select aria-label={`תפקיד חלופי ל${role}`} value={(fallbacks[role] ?? [])[0] ?? ""} onChange={(e) => {
                const next = { ...fallbacks };
                if (e.target.value) next[role] = [e.target.value];
                else delete next[role];
                onChange({ ...policy, role_fallbacks: next });
              }}>
                <option value="">אין</option>
                {roles.filter((other) => other !== role).map((other) => <option key={other} value={other}>{other}</option>)}
              </select>
            </div>
          ))}
        </div>
      ) : null}
      <p className="rotation-derived-note">שבוע נספר מראשון עד שבת. מקסימום הוא חובה בשיבוץ; מינימום הוא יעד. תפקיד חלופי ממלא מקום רק כשאין מספיק כשירים, ובעדיפות שנייה.</p>
    </>
  );
}

/** One person's dated qualifications (competence and service type are
 *  `SoldierFields`'). */
export function PersonStandard({ person, onChange }: { person: Row; onChange: (key: string, value: unknown) => void }) {
  const quals = Array.isArray(person.qualifications) ? person.qualifications as { role: string; last_active: string }[] : [];
  const setQual = (index: number, key: "role" | "last_active", value: string) =>
    onChange("qualifications", quals.map((row, at) => at === index ? { ...row, [key]: value } : row));
  return (
    <div className="manual-row-foot">
      {quals.map((row, index) => (
        <span className="manual-rule" key={index}>
          <input aria-label="כשירות לתפקיד" value={row.role} placeholder="תפקיד" onChange={(e) => setQual(index, "role", e.target.value)} />
          <input aria-label="פעילות אחרונה" type="date" value={row.last_active} onChange={(e) => setQual(index, "last_active", e.target.value)} />
          <button type="button" className="icon-button subtle" aria-label="הסרת כשירות" onClick={() => onChange("qualifications", quals.filter((_, at) => at !== index))}>×</button>
        </span>
      ))}
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
