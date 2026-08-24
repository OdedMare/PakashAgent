"use client";

import {
  CalendarClock,
  Clock3,
  Plus,
  Save,
  Scale,
  ShieldCheck,
  Trash2,
  Users,
  X,
} from "lucide-react";
import { useMemo, useState } from "react";

import { DateInput } from "@/components/DateInput";
import { updateProfile } from "@/services/api";
import type { TeamView, WorkplaceProfile } from "@/types";

const DAYS = ["ראשון", "שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת"];
const SERVICE_TYPES = {
  standard: "תקן",
  overlap: "נחפף/ת",
  reserve: "מילואים",
} as const;
const SHIFT_TYPES = {
  regular: "רגילה",
  overlap: "חפיפה",
  on_call: "כוננות",
} as const;
const EXIT_PATTERNS = {
  round: "סבב א / ב",
  triplet: "תלתון א / ב / ג",
  hamshushim: "חמשושים",
  shushim: "שושים",
} as const;

type Row = Record<string, unknown>;

/** Full first-time or follow-up setup. Saving calls no model. */
export function ManualSetup({
  workspace,
  onDone,
  onCancel,
}: {
  workspace: TeamView;
  onDone: () => void | Promise<void>;
  onCancel?: () => void;
}) {
  const profile = workspace.profile ?? {};
  const initialWorkplace = record(profile.workplace);
  const [unitName, setUnitName] = useState(text(initialWorkplace.name) || workspace.name);
  const [planningHorizon, setPlanningHorizon] = useState(text(initialWorkplace.planning_horizon) || "שבוע");
  const [operatingDays, setOperatingDays] = useState<string[]>(
    strings(initialWorkplace.operating_days).length
      ? strings(initialWorkplace.operating_days)
      : DAYS,
  );
  const [rotationMode] = useState<"round" | "triplet">(
    initialWorkplace.rotation_mode === "triplet" ? "triplet" : "round",
  );
  const [firstClosureGroup, setFirstClosureGroup] = useState(
    text(initialWorkplace.first_closure_group) || "א",
  );
  const [firstClosureDate, setFirstClosureDate] = useState(
    text(initialWorkplace.first_closure_date),
  );
  const [generalExitSchedule, setGeneralExitSchedule] = useState(
    inputText(initialWorkplace.general_exit_schedule),
  );
  const [employees, setEmployees] = useState<Row[]>(rows(profile.employees));
  const [shifts, setShifts] = useState<Row[]>(rows(profile.shifts));
  const [rules, setRules] = useState<Row[]>(rows(profile.rules));
  const audit = record(profile.audit_policy);
  const [maxWeeklyHours, setMaxWeeklyHours] = useState(number(audit.max_weekly_hours, 45));
  const [maxConsecutiveDays, setMaxConsecutiveDays] = useState(number(audit.max_consecutive_days, 6));
  const [minRestHours, setMinRestHours] = useState(number(audit.min_rest_hours, 8));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const shiftNames = useMemo(
    () => shifts.map((shift) => text(shift.name)).filter(Boolean),
    [shifts],
  );
  const originalEmployees = useMemo(
    () => new Set(rows(profile.employees).map((row) => text(row.name))),
    [profile.employees],
  );
  const originalShifts = useMemo(
    () => new Set(rows(profile.shifts).map((row) => text(row.name))),
    [profile.shifts],
  );
  const ready = Boolean(unitName.trim() && employees.some(named) && shifts.some(named));

  const save = async () => {
    if (!ready || busy) return;
    setBusy(true);
    setError("");
    try {
      await updateProfile({
        workplace: {
          ...initialWorkplace,
          name: unitName.trim(),
          planning_horizon: planningHorizon.trim() || "שבוע",
          operating_days: operatingDays,
          rotation_mode: rotationMode,
          first_closure_group: firstClosureGroup,
          first_closure_date: firstClosureDate,
          general_exit_schedule: generalExitSchedule.trim(),
        },
        employees: employees.filter(named).map((person) => ({
          ...person,
          name: text(person.name),
          role: text(person.role),
          exit_pattern: exitPattern(person),
          rotation_group: rotationGroups(exitPattern(person)).includes(text(person.rotation_group))
            ? text(person.rotation_group)
            : rotationGroups(exitPattern(person))[0] ?? "",
          service_type: text(person.service_type) || "standard",
          counts_toward_staffing: person.counts_toward_staffing !== false,
          eligible_shifts: strings(person.eligible_shifts),
          is_shift_manager: Boolean(person.is_shift_manager),
          can_train: Boolean(person.can_train),
          notes: text(person.notes),
        })),
        shifts: shifts.filter(named).map((shift) => ({
          ...shift,
          name: text(shift.name),
          purpose: text(shift.purpose),
          shift_type: text(shift.shift_type) || "regular",
          start_time: text(shift.start_time),
          end_time: text(shift.end_time),
          days: strings(shift.days),
          headcount: number(shift.headcount, headcount(shift)),
          requires_shift_manager: Boolean(shift.requires_shift_manager),
        })),
        rules: rules
          .filter((rule) => text(rule.text))
          .map((rule) => ({
            text: text(rule.text),
            priority: rule.priority === "soft" ? "soft" : "hard",
          })),
        audit_policy: {
          max_weekly_hours: maxWeeklyHours,
          max_consecutive_days: maxConsecutiveDays,
          min_rest_hours: minRestHours,
        },
        summary: "יחידה צבאית עם מבנה יציאות אישי לכל חייל/ת",
      });
      await onDone();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "לא ניתן לשמור את ההגדרות");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="manual-setup">
      <header className="manual-setup-header">
        <div>
          <span className="manual-kicker">הגדרה ידנית · ללא שימוש במודל</span>
          <h1>בונים את שיטת השיבוץ של היחידה</h1>
          <p>כל מה שמוגדר כאן נכנס ישירות לפרופיל שממנו נבנים הסידורים.</p>
        </div>
        <div className="manual-header-actions">
          {onCancel ? (
            <button type="button" className="ghost-button" onClick={onCancel} disabled={busy}>
              <X size={16} /> ביטול
            </button>
          ) : null}
          <button type="button" className="primary-button" onClick={() => void save()} disabled={!ready || busy}>
            <Save size={16} /> {busy ? "שומר…" : "שמירת ההגדרות"}
          </button>
        </div>
      </header>

      {error ? <div className="manual-error" role="alert">{error}</div> : null}

      <main id="main-content" className="manual-sections">
        <SetupSection icon={<CalendarClock />} title="היחידה והיציאות הכלליות" hint="מתארים כאן את תמונת היציאות של הצוות; את המבנה האישי מגדירים לכל חייל/ת בנפרד.">
          <div className="manual-grid three">
            <Field label="שם היחידה *">
              <input value={unitName} onChange={(event) => setUnitName(event.target.value)} maxLength={120} required />
            </Field>
            <Field label="אורך סידור">
              <select value={planningHorizon} onChange={(event) => setPlanningHorizon(event.target.value)}>
                <option value="שבוע">שבוע</option><option value="שבועיים">שבועיים</option><option value="חודש">חודש</option>
              </select>
            </Field>
            <Field label="קבוצת עוגן (לסבבים)">
              <select value={firstClosureGroup} onChange={(event) => setFirstClosureGroup(event.target.value)}>
                {(rotationMode === "triplet" ? ["א", "ב", "ג"] : ["א", "ב"]).map((group) => <option key={group} value={group}>{group}</option>)}
              </select>
            </Field>
            <Field label="תאריך עוגן (רשות)">
              <DateInput value={firstClosureDate} onChange={setFirstClosureDate} />
            </Field>
          </div>
          <Field label="היציאות הכלליות של הצוות">
            <textarea value={generalExitSchedule} onChange={(event) => setGeneralExitSchedule(event.target.value)} rows={3} placeholder="לדוגמה: השבוע צוות א סוגר; חמשושים יוצאים בחמישי ב־10:00 וחוזרים בראשון ב־08:00" />
          </Field>
          <CheckboxGrid label="ימי פעילות" values={DAYS} selected={operatingDays} onChange={setOperatingDays} />
        </SetupSection>

        <SetupSection icon={<Users />} title="כוח אדם" hint="לכל אדם מגדירים יציאות משלו, יכולות, מעמד והערות.">
          <div className="manual-list">
            {employees.map((person, index) => (
              <article className="manual-row" key={`employee-${index}`}>
                <div className="manual-grid employee-grid">
                  <Field label="שם *"><input value={inputText(person.name)} readOnly={originalEmployees.has(text(person.name))} onChange={(e) => edit(setEmployees, index, "name", e.target.value)} /></Field>
                  <Field label="תפקיד"><input value={inputText(person.role)} onChange={(e) => edit(setEmployees, index, "role", e.target.value)} /></Field>
                  <Field label="מבנה יציאות">
                    <select value={exitPattern(person)} onChange={(e) => {
                      edit(setEmployees, index, "exit_pattern", e.target.value);
                      edit(setEmployees, index, "rotation_group", rotationGroups(e.target.value)[0] ?? "");
                    }}>{Object.entries(EXIT_PATTERNS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select>
                  </Field>
                  {rotationGroups(exitPattern(person)).length ? <Field label="קבוצה"><select value={text(person.rotation_group) || rotationGroups(exitPattern(person))[0]} onChange={(e) => edit(setEmployees, index, "rotation_group", e.target.value)}>{rotationGroups(exitPattern(person)).map((group) => <option key={group}>{group}</option>)}</select></Field> : null}
                  <Field label="מעמד">
                    <select value={text(person.service_type) || "standard"} onChange={(e) => {
                      edit(setEmployees, index, "service_type", e.target.value);
                      edit(setEmployees, index, "counts_toward_staffing", e.target.value !== "overlap");
                    }}>{Object.entries(SERVICE_TYPES).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select>
                  </Field>
                </div>
                <div className="manual-row-foot">
                  <label className="manual-check"><input type="checkbox" checked={person.counts_toward_staffing !== false} onChange={(e) => edit(setEmployees, index, "counts_toward_staffing", e.target.checked)} /><span>נספר/ת בתקן</span></label>
                  <label className="manual-check"><input type="checkbox" checked={Boolean(person.is_shift_manager)} onChange={(e) => edit(setEmployees, index, "is_shift_manager", e.target.checked)} /><span>מוסמך/ת כמפקד/ת משמרת</span></label>
                  <label className="manual-check"><input type="checkbox" checked={Boolean(person.can_train)} onChange={(e) => edit(setEmployees, index, "can_train", e.target.checked)} /><span>מוסמך/ת לחפוף</span></label>
                  <div className="manual-shift-picks" aria-label="משמרות מותרות">
                    {shiftNames.map((shift) => <label key={shift}><input type="checkbox" checked={strings(person.eligible_shifts).includes(shift)} onChange={(e) => toggleRowList(setEmployees, index, "eligible_shifts", shift, e.target.checked)} /><span>{shift}</span></label>)}
                  </div>
                  <button type="button" className="icon-button subtle" aria-label="מחיקת איש צוות" disabled={originalEmployees.has(text(person.name))} onClick={() => setEmployees((current) => current.filter((_, row) => row !== index))}><Trash2 size={15} /></button>
                </div>
                <Field label="הערות לחייל/ת"><textarea value={inputText(person.notes)} onChange={(e) => edit(setEmployees, index, "notes", e.target.value)} rows={2} placeholder="מידע קבוע שכדאי לקחת בחשבון בשיבוץ" /></Field>
              </article>
            ))}
          </div>
          <button type="button" className="ghost-button" onClick={() => setEmployees((current) => [...current, { name: "", role: "", exit_pattern: "round", rotation_group: "א", service_type: "standard", counts_toward_staffing: true, eligible_shifts: [], is_shift_manager: false, can_train: false, notes: "" }])}><Plus size={16} /> הוספת איש/אשת צוות</button>
        </SetupSection>

        <SetupSection icon={<Clock3 />} title="סוגי משמרות ותקינה" hint="משמרת חפיפה מוצגת בנפרד; מי שלא נספר בתקן לא ממלא את המכסה.">
          <div className="manual-list">
            {shifts.map((shift, index) => (
              <article className="manual-row" key={`shift-${index}`}>
                <div className="manual-grid shift-grid">
                  <Field label="שם המשמרת *"><input value={inputText(shift.name)} readOnly={originalShifts.has(text(shift.name))} onChange={(e) => edit(setShifts, index, "name", e.target.value)} /></Field>
                  <Field label="סוג"><select value={text(shift.shift_type) || (shift.is_on_call ? "on_call" : "regular")} onChange={(e) => edit(setShifts, index, "shift_type", e.target.value)}>{Object.entries(SHIFT_TYPES).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></Field>
                  <Field label="התחלה"><input type="time" step={300} value={text(shift.start_time)} onChange={(e) => edit(setShifts, index, "start_time", e.target.value)} /></Field>
                  <Field label="סיום"><input type="time" step={300} value={text(shift.end_time)} onChange={(e) => edit(setShifts, index, "end_time", e.target.value)} /></Field>
                  <Field label="תקן"><input type="number" min={1} max={100} value={number(shift.headcount, headcount(shift))} onChange={(e) => edit(setShifts, index, "headcount", Number(e.target.value) || 1)} /></Field>
                  <Field label="ייעוד"><input value={inputText(shift.purpose)} onChange={(e) => edit(setShifts, index, "purpose", e.target.value)} placeholder="סיור, חמ״ל, חפיפה…" /></Field>
                </div>
                <label className="manual-check"><input type="checkbox" checked={Boolean(shift.requires_shift_manager)} onChange={(e) => edit(setShifts, index, "requires_shift_manager", e.target.checked)} /><span>נדרש/ת מפקד/ת משמרת מוסמך/ת</span></label>
                <CheckboxGrid label="ימים" values={DAYS} selected={strings(shift.days)} onChange={(value) => edit(setShifts, index, "days", value)} />
                <button type="button" className="icon-button subtle manual-delete" aria-label="מחיקת סוג משמרת" disabled={originalShifts.has(text(shift.name))} onClick={() => setShifts((current) => current.filter((_, row) => row !== index))}><Trash2 size={15} /></button>
              </article>
            ))}
          </div>
          <button type="button" className="ghost-button" onClick={() => setShifts((current) => [...current, { name: "", shift_type: "regular", start_time: "", end_time: "", headcount: 1, purpose: "", days: DAYS }])}><Plus size={16} /> הוספת סוג משמרת</button>
        </SetupSection>

        <SetupSection icon={<ShieldCheck />} title="כללים קבועים" hint="כלל קשיח הוא חובה; כלל רך הוא העדפה שהמערכת מנסה לכבד.">
          <div className="manual-list compact">
            {rules.map((rule, index) => (
              <div className="manual-rule" key={index}>
                <input aria-label="ניסוח הכלל" value={inputText(rule.text)} onChange={(e) => edit(setRules, index, "text", e.target.value)} placeholder="לדוגמה: אין לשבץ חפיפה מיד אחרי לילה" />
                <select aria-label="עוצמת הכלל" value={rule.priority === "soft" ? "soft" : "hard"} onChange={(e) => edit(setRules, index, "priority", e.target.value)}><option value="hard">קשיח</option><option value="soft">העדפה</option></select>
                <button type="button" className="icon-button subtle" aria-label="מחיקת כלל" onClick={() => setRules((current) => current.filter((_, row) => row !== index))}><Trash2 size={15} /></button>
              </div>
            ))}
          </div>
          <button type="button" className="ghost-button" onClick={() => setRules((current) => [...current, { text: "", priority: "hard" }])}><Plus size={16} /> הוספת כלל קבוע</button>
        </SetupSection>

        <SetupSection icon={<Scale />} title="גבולות עומס ומנוחה" hint="בדיקות אלה מציפות חריגות ומסייעות לשיבוץ; הן אינן חוסמות החלטת מפקד.">
          <div className="manual-grid three">
            <Field label="מקסימום שעות בשבוע"><input type="number" min={1} value={maxWeeklyHours} onChange={(e) => setMaxWeeklyHours(Number(e.target.value) || 1)} /></Field>
            <Field label="מקסימום ימים רצופים"><input type="number" min={1} value={maxConsecutiveDays} onChange={(e) => setMaxConsecutiveDays(Number(e.target.value) || 1)} /></Field>
            <Field label="מינימום מנוחה בין משמרות"><input type="number" min={0} value={minRestHours} onChange={(e) => setMinRestHours(Number(e.target.value) || 0)} /></Field>
          </div>
        </SetupSection>
      </main>

      <footer className="manual-savebar">
        <span>{employees.filter(named).length} אנשי צוות · {shifts.filter(named).length} סוגי משמרות · {rules.filter((rule) => text(rule.text)).length} כללים</span>
        <button type="button" className="primary-button" onClick={() => void save()} disabled={!ready || busy}><Save size={16} /> {busy ? "שומר…" : "שמירה ומעבר ללוח"}</button>
      </footer>
    </div>
  );
}

function SetupSection({ icon, title, hint, children }: { icon: React.ReactNode; title: string; hint: string; children: React.ReactNode }) {
  return <section className="manual-section"><header><span>{icon}</span><div><h2>{title}</h2><p>{hint}</p></div></header><div className="manual-section-body">{children}</div></section>;
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <label className="manual-field"><span>{label}</span>{children}</label>;
}

function CheckboxGrid({ label, values, selected, onChange }: { label: string; values: string[]; selected: string[]; onChange: (value: string[]) => void }) {
  return <fieldset className="manual-checkboxes"><legend>{label}</legend>{values.map((value) => <label key={value}><input type="checkbox" checked={selected.includes(value)} onChange={(event) => onChange(event.target.checked ? [...selected, value] : selected.filter((item) => item !== value))} /><span>{value}</span></label>)}</fieldset>;
}

function edit(setter: React.Dispatch<React.SetStateAction<Row[]>>, index: number, key: string, value: unknown) {
  setter((current) => current.map((row, rowIndex) => rowIndex === index ? { ...row, [key]: value } : row));
}

function toggleRowList(setter: React.Dispatch<React.SetStateAction<Row[]>>, index: number, key: string, value: string, checked: boolean) {
  setter((current) => current.map((row, rowIndex) => rowIndex === index ? { ...row, [key]: checked ? [...strings(row[key]), value] : strings(row[key]).filter((item) => item !== value) } : row));
}

function record(value: unknown): Row { return value && typeof value === "object" && !Array.isArray(value) ? value as Row : {}; }
function rows(value: unknown): Row[] { return Array.isArray(value) ? value.filter((item): item is Row => Boolean(item) && typeof item === "object" && !Array.isArray(item)) : []; }
function strings(value: unknown): string[] { return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string" && Boolean(item.trim())) : []; }
function text(value: unknown): string { return typeof value === "string" ? value.trim() : ""; }
function inputText(value: unknown): string { return typeof value === "string" ? value : ""; }
function exitPattern(row: Row): keyof typeof EXIT_PATTERNS {
  const value = text(row.exit_pattern);
  return value in EXIT_PATTERNS ? value as keyof typeof EXIT_PATTERNS : "round";
}
function rotationGroups(pattern: string): string[] {
  if (pattern === "triplet") return ["א", "ב", "ג"];
  if (pattern === "round") return ["א", "ב"];
  return [];
}
function number(value: unknown, fallback: number): number { return typeof value === "number" && Number.isFinite(value) ? value : fallback; }
function named(row: Row): boolean { return Boolean(text(row.name)); }
function headcount(shift: Row): number {
  const staffing = rows(shift.staffing);
  const base = staffing.find((group) => strings(group.days).length === 0);
  return number(base?.headcount, 1);
}
