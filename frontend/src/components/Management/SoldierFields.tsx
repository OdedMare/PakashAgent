"use client";

/** A soldier's competence, and the days a week a reservist — or a standard
 *  officer or NCO — comes.
 *
 *  Competence is optional for everyone and lives under "פרמטרים מתקדמים":
 *  the solver balances each shift by it so the weaker soldiers are not
 *  staffed together. Choosing "מילואים" opens the three questions a
 *  reservist owes — days a week (a hard cap per Sunday–Saturday week),
 *  call-up type, and competence — in place of that drawer, and two optional
 *  ones for a reservist whose days change week to week: a minimum the
 *  solver tries to reach, and whether the days must run in one block. The
 *  solver picks which days. A standard officer or NCO (קצין/ה, נגד/ת under
 *  מעמד) gets the same days questions, without the call-up type: five days
 *  a week, say, like a reservist. אע״צ and הצ״ח see competence directly
 *  too, not folded into the drawer.
 *
 *  `serviceType` is the merged מעמד value (`statusOf`), not the raw
 *  `service_type`. */

export const COMPETENCE_LABELS: Record<string, string> = {
  weak: "חלש/ה",
  medium: "בינוני/ת",
  high: "גבוה/ה",
  excellent: "מצטיין/ת",
};

/** A strong shift: the lowest רמה מקצועית that belongs on it
 *  (`min_competence`). The solver puts stronger soldiers there first and the
 *  board names anybody below it on their own card. */
export const SHIFT_LEVEL_LABELS: Record<string, string> = {
  "": "כל רמה",
  medium: "בינונית ומעלה",
  high: "גבוהה ומעלה",
  excellent: "מצטיינים בלבד",
};

export function ShiftLevelSelect({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  return (
    <select value={value} onChange={(event) => onChange(event.target.value)}>
      {Object.entries(SHIFT_LEVEL_LABELS).map(([level, label]) => <option key={level} value={level}>{label}</option>)}
    </select>
  );
}

/** "מעמד" is one choice: the service type and, for a standard soldier,
 *  the rank (`rank_group`). An officer or NCO is stored as
 *  `service_type: "standard"` plus `rank_group`, so the server and the
 *  solver read the two fields exactly as before. */
export const STATUS_LABELS: Record<string, string> = {
  standard: "סדיר",
  officer: "קצין/ה",
  nco: "נגד/ת",
  overlap: "נחפף/ת",
  reserve: "מילואים",
  civilian: "אע״צ",
  hatzach: "הצ״ח",
};

const RANKS = new Set(["officer", "nco"]);

/** The one "מעמד" value for a person's `service_type` and `rank_group`. */
export function statusOf(serviceType: unknown, rankGroup: unknown): string {
  const service = typeof serviceType === "string" && serviceType ? serviceType : "standard";
  const rank = typeof rankGroup === "string" ? rankGroup : "";
  return service === "standard" && RANKS.has(rank) ? rank : service;
}

/** The two stored fields a "מעמד" choice stands for. */
export function statusFields(status: string): { service_type: string; rank_group: string } {
  return RANKS.has(status)
    ? { service_type: "standard", rank_group: status }
    : { service_type: status || "standard", rank_group: "" };
}

/** Whether this status comes a set number of days a week: a reservist, or
 *  a standard officer or NCO (five days a week, say). */
export function comesDaysAWeek(status: string): boolean {
  return status === "reserve" || RANKS.has(status);
}

export const RESERVE_CALL_LABELS: Record<string, string> = {
  order: "צו",
  days: "ימי מילואים",
};

export type SoldierField = "competence" | "reserve_days_per_week" | "reserve_min_days" | "reserve_consecutive" | "reserve_call";

const dayCount = (days: number) => (days === 1 ? "יום אחד" : `${days} ימים`);

export function SoldierFields({
  serviceType,
  competence,
  reserveDays,
  reserveMinDays,
  reserveConsecutive,
  reserveCall,
  onChange,
}: {
  serviceType: string;
  competence: string;
  reserveDays: number | null;
  reserveMinDays: number | null;
  reserveConsecutive: boolean;
  reserveCall: string;
  onChange: (field: SoldierField, value: string | number | boolean | null) => void;
}) {
  const competenceField = (
    <label className="soldier-field">
      <span>רמה מקצועית</span>
      <select value={competence} onChange={(event) => onChange("competence", event.target.value)}>
        <option value="">לא מוגדרת</option>
        {Object.entries(COMPETENCE_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select>
    </label>
  );

  if (comesDaysAWeek(serviceType)) {
    const reserve = serviceType === "reserve";
    return (
      <fieldset className="soldier-reserve">
        <legend>{reserve ? "פרטי מילואים" : `ימים בשבוע · ${STATUS_LABELS[serviceType]}`}</legend>
        <div className="soldier-grid">
          <label className="soldier-field">
            <span>כמה ימים בשבוע יכול/ה להגיע</span>
            <select
              value={reserveDays ?? ""}
              onChange={(event) => {
                const days = event.target.value ? Number(event.target.value) : null;
                onChange("reserve_days_per_week", days);
                if (days !== null && reserveMinDays !== null && reserveMinDays > days) onChange("reserve_min_days", days);
              }}
            >
              <option value="">{reserve ? "לא ידוע" : "ללא הגבלה"}</option>
              {[1, 2, 3, 4, 5, 6, 7].map((days) => <option key={days} value={days}>{dayCount(days)}</option>)}
            </select>
          </label>
          <label className="soldier-field">
            <span>לפחות (רשות)</span>
            <select
              value={reserveMinDays ?? ""}
              onChange={(event) => onChange("reserve_min_days", event.target.value ? Number(event.target.value) : null)}
            >
              <option value="">ללא מינימום</option>
              {[1, 2, 3, 4, 5, 6, 7].filter((days) => reserveDays === null || days <= reserveDays)
                .map((days) => <option key={days} value={days}>{dayCount(days)}</option>)}
            </select>
          </label>
          {reserve ? (
            <label className="soldier-field">
              <span>צו או ימי מילואים</span>
              <select value={reserveCall} onChange={(event) => onChange("reserve_call", event.target.value)}>
                <option value="">לא צוין</option>
                {Object.entries(RESERVE_CALL_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </label>
          ) : null}
          {competenceField}
        </div>
        <label className="profile-check">
          <input type="checkbox" checked={reserveConsecutive} onChange={(event) => onChange("reserve_consecutive", event.target.checked)} />
          <span>הימים ברצף (בלי ימים בודדים באמצע השבוע)</span>
        </label>
        <small>{reserve ? "" : "לא חובה. "}מספר הימים הוא תקרה קשיחה לכל שבוע (ראשון–שבת). המינימום הוא יעד: הסידור ישבץ לפחות כך, אלא אם אין משמרות פנויות או שהחייל/ת לא זמין/ה. את הימים עצמם בוחר הסידור לפי הצורך.</small>
      </fieldset>
    );
  }

  if (serviceType === "civilian" || serviceType === "hatzach") {
    return (
      <fieldset className="soldier-reserve">
        <legend>{serviceType === "civilian" ? "פרטי אע״צ" : "פרטי הצ״ח"}</legend>
        <div className="soldier-grid">{competenceField}</div>
        <small>לא חובה. הסידור יאזן את המשמרות כך שבעלי רמה מקצועית חלשה יחסית לא ישובצו יחד.</small>
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

/** "רמה מקצועית: גבוה/ה · מילואים 3 ימים, צו" — the roster card's short line. */
export function soldierSummary(person: Record<string, unknown> | undefined): string {
  if (!person) return "";
  const parts: string[] = [];
  const competence = typeof person.competence === "string" ? person.competence : "";
  if (COMPETENCE_LABELS[competence]) parts.push(`רמה מקצועית: ${COMPETENCE_LABELS[competence]}`);
  const status = statusOf(person.service_type, person.rank_group);
  if (comesDaysAWeek(status)) {
    const days = typeof person.reserve_days_per_week === "number" ? person.reserve_days_per_week : null;
    const least = typeof person.reserve_min_days === "number" ? person.reserve_min_days : null;
    const call = status === "reserve" && typeof person.reserve_call === "string" ? RESERVE_CALL_LABELS[person.reserve_call] : "";
    const span = days && least && least < days ? `${least}–${days} ימים בשבוע` : days ? `${days} ימים בשבוע` : least ? `לפחות ${least} ימים בשבוע` : "";
    const reserve = [span, person.reserve_consecutive === true ? "ברצף" : "", call ?? ""].filter(Boolean).join(", ");
    if (reserve) parts.push(`${status === "reserve" ? "מילואים" : STATUS_LABELS[status]}: ${reserve}`);
  }
  return parts.join(" · ");
}
