"use client";

/** A soldier's competence, and a reservist's call-up questions.
 *
 *  Competence is optional for everyone and lives under "פרמטרים מתקדמים":
 *  the solver balances each shift by it so the weaker soldiers are not
 *  staffed together. Choosing "מילואים" opens the three questions a
 *  reservist owes — days a week (a hard cap per Sunday–Saturday week),
 *  call-up type, and competence — in place of that drawer. */

export const COMPETENCE_LABELS: Record<string, string> = {
  weak: "חלש/ה",
  medium: "בינוני/ת",
  high: "גבוה/ה",
  excellent: "מצטיין/ת",
};

export const RESERVE_CALL_LABELS: Record<string, string> = {
  order: "צו",
  days: "ימי מילואים",
};

export type SoldierField = "competence" | "reserve_days_per_week" | "reserve_call";

export function SoldierFields({
  serviceType,
  competence,
  reserveDays,
  reserveCall,
  onChange,
}: {
  serviceType: string;
  competence: string;
  reserveDays: number | null;
  reserveCall: string;
  onChange: (field: SoldierField, value: string | number | null) => void;
}) {
  const competenceField = (
    <label className="soldier-field">
      <span>כשירות</span>
      <select value={competence} onChange={(event) => onChange("competence", event.target.value)}>
        <option value="">לא מוגדרת</option>
        {Object.entries(COMPETENCE_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select>
    </label>
  );

  if (serviceType === "reserve") {
    return (
      <fieldset className="soldier-reserve">
        <legend>פרטי מילואים</legend>
        <div className="soldier-grid">
          <label className="soldier-field">
            <span>כמה ימים בשבוע יכול/ה להגיע</span>
            <select
              value={reserveDays ?? ""}
              onChange={(event) => onChange("reserve_days_per_week", event.target.value ? Number(event.target.value) : null)}
            >
              <option value="">לא ידוע</option>
              {[1, 2, 3, 4, 5, 6, 7].map((days) => <option key={days} value={days}>{days === 1 ? "יום אחד" : `${days} ימים`}</option>)}
            </select>
          </label>
          <label className="soldier-field">
            <span>צו או ימי מילואים</span>
            <select value={reserveCall} onChange={(event) => onChange("reserve_call", event.target.value)}>
              <option value="">לא צוין</option>
              {Object.entries(RESERVE_CALL_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </label>
          {competenceField}
        </div>
        <small>מספר הימים הוא תקרה קשיחה לכל שבוע (ראשון–שבת) בבניית הסידור.</small>
      </fieldset>
    );
  }

  return (
    <details className="soldier-advanced" open={Boolean(competence) || undefined}>
      <summary>פרמטרים מתקדמים</summary>
      <div className="soldier-grid">{competenceField}</div>
      <small>לא חובה. הסידור יאזן את המשמרות כך שחיילים חלשים יחסית לא ישובצו יחד.</small>
    </details>
  );
}

/** "כשירות גבוה/ה · מילואים 3 ימים, צו" — the roster card's short line. */
export function soldierSummary(person: Record<string, unknown> | undefined): string {
  if (!person) return "";
  const parts: string[] = [];
  const competence = typeof person.competence === "string" ? person.competence : "";
  if (COMPETENCE_LABELS[competence]) parts.push(`כשירות ${COMPETENCE_LABELS[competence]}`);
  if (person.service_type === "reserve") {
    const days = typeof person.reserve_days_per_week === "number" ? person.reserve_days_per_week : null;
    const call = typeof person.reserve_call === "string" ? RESERVE_CALL_LABELS[person.reserve_call] : "";
    const reserve = [days ? `${days} ימים בשבוע` : "", call ?? ""].filter(Boolean).join(", ");
    if (reserve) parts.push(`מילואים: ${reserve}`);
  }
  return parts.join(" · ");
}
