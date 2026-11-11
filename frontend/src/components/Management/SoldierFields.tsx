"use client";

/** A soldier's competence, and the days a week a reservist — or a standard
 *  officer or NCO — comes.
 *
 *  Competence is optional for everyone and lives under "פרמטרים מתקדמים":
 *  the solver balances each shift by it so the weaker soldiers are not
 *  staffed together. Choosing "מילואים" opens a reservist's questions —
 *  call-up type and competence — in place of that drawer, and two optional
 *  ones: a minimum of days a week the solver tries to reach, and whether
 *  the days must run in one block. A reservist can come any day except the
 *  fixed blocked weekdays ticked under them ("לא יכול/ה להגיע ברביעי" —
 *  `lib/blockedDays.ts`, stored as a recurring constraint); they are not
 *  asked for a number of days a week, and the forms save none
 *  (`daysCapOf`). A standard officer or NCO (קצין/ה, נגד/ת under מעמד) is
 *  asked that number as well — a hard cap in any seven consecutive days,
 *  five days a week, say — and takes no call-up type. אע״צ and הצ״ח see
 *  competence directly too, not folded into the drawer.
 *
 *  `serviceType` is the merged מעמד value (`statusOf`), not the raw
 *  `service_type`. */

import { WEEKDAY_NAMES, blockedDaysOf } from "@/lib/blockedDays";

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

/** How much one shift of this kind weighs when the solver evens the load
 *  (`load_weight`). Empty is the default: 1.5 for a night, 1 for anything
 *  else (an on-call night counts 1). The list stops at 1.75 so one shift of
 *  evenness never outweighs a soldier's soft request. */
export const LOAD_WEIGHT_LABELS: [string, string][] = [
  ["", "ברירת מחדל (לילה 1.5, אחרת 1)"],
  ["0.5", "0.5 — קלה"],
  ["0.75", "0.75"],
  ["1", "1 — רגילה"],
  ["1.25", "1.25"],
  ["1.5", "1.5 — כבדה"],
  ["1.75", "1.75 — כבדה מאוד"],
];

/** The stored weight as the select's value: "" for the default. */
export function loadWeightValue(value: unknown): string {
  return typeof value === "number" && Number.isFinite(value) ? String(value) : "";
}

/** The select's value as the profile stores it: null for the default. */
export function loadWeightOf(value: string): number | null {
  return value === "" ? null : Number(value);
}

export function LoadWeightSelect({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  return (
    <select value={value} onChange={(event) => onChange(event.target.value)}>
      {LOAD_WEIGHT_LABELS.map(([weight, label]) => <option key={weight} value={weight}>{label}</option>)}
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

/** The `reserve_days_per_week` a form saves: the number typed for an
 *  officer or NCO, none for a reservist — they come any day they are not
 *  blocked, and a cap nobody can see or change would be a hidden rule. */
export function daysCapOf(status: string, days: unknown): number | null {
  return RANKS.has(status) && typeof days === "number" ? days : null;
}

export const RESERVE_CALL_LABELS: Record<string, string> = {
  order: "צו",
  days: "ימי מילואים",
};

export type SoldierField = "competence" | "reserve_days_per_week" | "reserve_min_days" | "reserve_consecutive" | "reserve_call"
  | "min_weekly_shifts" | "max_weekly_shifts";

type StatusFieldsProps = {
  serviceType: string;
  competence: string;
  reserveDays: number | null;
  reserveMinDays: number | null;
  reserveConsecutive: boolean;
  reserveCall: string;
  /** The weekdays they can never come (`blockedDaysOf`), and the setter that
   *  rewrites the person's `recurring_constraints` (`withBlockedDays`). */
  blockedDays: string[];
  onBlockedDays: (days: string[]) => void;
  onChange: (field: SoldierField, value: string | number | boolean | null) => void;
};

/** A weekly shift limit typed in a box: a whole number from `least` to 14,
 *  or null for blank — the soldier is then on their מעמד's number. */
export function shiftCount(value: string, least = 0): number | null {
  if (value.trim() === "") return null;
  const parsed = Math.trunc(Number(value));
  return Number.isFinite(parsed) ? Math.min(14, Math.max(least, parsed)) : null;
}

/** The soldier's status fields, then their own weekly minimum and maximum
 *  of shifts (Sunday–Saturday), over the unit's numbers for their מעמד.
 *  A נחפף/ת fills no seat and takes none. */
export function SoldierFields({
  minShifts,
  maxShifts,
  ...props
}: StatusFieldsProps & { minShifts: number | null; maxShifts: number | null }) {
  return (
    <>
      <SoldierStatusFields {...props} />
      {props.serviceType === "overlap" ? null : (
        <fieldset className="soldier-reserve">
          <legend>משמרות בשבוע</legend>
          <div className="soldier-grid">
            <label className="soldier-field">
              <span>מינימום משמרות</span>
              <input type="number" min={0} max={14} inputMode="numeric" value={minShifts ?? ""} placeholder="לפי המעמד"
                onChange={(event) => props.onChange("min_weekly_shifts", shiftCount(event.target.value))} />
            </label>
            <label className="soldier-field">
              <span>מקסימום משמרות</span>
              <input type="number" min={1} max={14} inputMode="numeric" value={maxShifts ?? ""} placeholder="לפי המעמד"
                onChange={(event) => props.onChange("max_weekly_shifts", shiftCount(event.target.value, 1))} />
            </label>
          </div>
          <small>לא חובה. שבוע ראשון–שבת. המקסימום נאכף בשיבוץ; המינימום הוא יעד שהסידור ישבץ אלא אם אין משמרות פנויות. ריק = לפי המעמד, כפי שהוגדר בגבולות העומס של היחידה.</small>
        </fieldset>
      )}
    </>
  );
}

const dayCount = (days: number) => (days === 1 ? "יום אחד" : `${days} ימים`);

function SoldierStatusFields({
  serviceType,
  competence,
  reserveDays,
  reserveMinDays,
  reserveConsecutive,
  reserveCall,
  blockedDays,
  onBlockedDays,
  onChange,
}: StatusFieldsProps) {
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
    const cap = daysCapOf(serviceType, reserveDays);
    return (
      <fieldset className="soldier-reserve">
        <legend>{reserve ? "פרטי מילואים" : `ימים בשבוע · ${STATUS_LABELS[serviceType]}`}</legend>
        <div className="soldier-grid">
          {reserve ? null : <label className="soldier-field">
            <span>כמה ימים בשבוע יכול/ה להגיע</span>
            <select
              value={reserveDays ?? ""}
              onChange={(event) => {
                const days = event.target.value ? Number(event.target.value) : null;
                onChange("reserve_days_per_week", days);
                if (days !== null && reserveMinDays !== null && reserveMinDays > days) onChange("reserve_min_days", days);
              }}
            >
              <option value="">ללא הגבלה</option>
              {[1, 2, 3, 4, 5, 6, 7].map((days) => <option key={days} value={days}>{dayCount(days)}</option>)}
            </select>
          </label>}
          <label className="soldier-field">
            <span>{reserve ? "לפחות ימים בשבוע (רשות)" : "לפחות (רשות)"}</span>
            <select
              value={reserveMinDays ?? ""}
              onChange={(event) => onChange("reserve_min_days", event.target.value ? Number(event.target.value) : null)}
            >
              <option value="">ללא מינימום</option>
              {[1, 2, 3, 4, 5, 6, 7].filter((days) => cap === null || days <= cap)
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
        <fieldset className="profile-checkboxes soldier-blocked-days">
          <legend>ימים חסומים קבועים — לא יכול/ה להגיע</legend>
          {WEEKDAY_NAMES.map((day) => (
            <label key={day}>
              <input type="checkbox" checked={blockedDays.includes(day)}
                onChange={(event) => onBlockedDays(event.target.checked ? [...blockedDays, day] : blockedDays.filter((value) => value !== day))} />
              <span>{day}</span>
            </label>
          ))}
        </fieldset>
        {blockedDays.length && (reserveMinDays ?? cap ?? 0) > 7 - blockedDays.length ? (
          <small className="soldier-blocked-warning">נשארו {dayCount(7 - blockedDays.length)} פנויים בשבוע — פחות ממספר הימים שהוגדר למעלה.</small>
        ) : null}
        <small>{reserve ? "יכול/ה להגיע בכל יום שלא סומן חסום. " : "לא חובה. מספר הימים הוא תקרה קשיחה בכל 7 ימים רצופים. "}המינימום הוא יעד לשבוע ראשון–שבת: הסידור ישבץ לפחות כך, אלא אם אין משמרות פנויות או שהחייל/ת לא זמין/ה. את הימים עצמם בוחר הסידור לפי הצורך, ולעולם לא ביום חסום: יום שסומן חסום בכל שבוע, בכל המשמרות שמתחילות בו.</small>
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
    const days = daysCapOf(status, person.reserve_days_per_week);
    const least = typeof person.reserve_min_days === "number" ? person.reserve_min_days : null;
    const call = status === "reserve" && typeof person.reserve_call === "string" ? RESERVE_CALL_LABELS[person.reserve_call] : "";
    const span = days && least && least < days ? `${least}–${days} ימים בשבוע` : days ? `${days} ימים בשבוע` : least ? `לפחות ${least} ימים בשבוע` : "";
    const reserve = [span, person.reserve_consecutive === true ? "ברצף" : "", call ?? ""].filter(Boolean).join(", ");
    if (reserve) parts.push(`${status === "reserve" ? "מילואים" : STATUS_LABELS[status]}: ${reserve}`);
    const blocked = blockedDaysOf(person.recurring_constraints);
    if (blocked.length) parts.push(`חסום/ה: ${blocked.join(", ")}`);
  }
  return parts.join(" · ");
}
