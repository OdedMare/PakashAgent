"use client";

import { useState } from "react";

import { DateInput } from "@/components/DateInput";
import { MultiSelect } from "@/components/MultiSelect";
import { TimeInput } from "@/components/TimeInput";
import { cycleOf, cyclePattern, isDayCycle } from "@/lib/dayCycles";
import type { DayCycle } from "@/types";

import { ExitPatternFields } from "./ExitPatternFields";
import { STATUS_LABELS, ShiftLevelSelect, SoldierFields, statusFields, statusOf } from "./SoldierFields";
import {
  EXIT_PATTERN_LABELS,
  text,
  rawText,
  patternGroups,
  shiftHeadcount,
} from "./teamLabels";

/** The roster's add/edit form for one person. Also used by the changes tab
 *  ("הוספת חייל"), so a soldier added there is the same record as one added
 *  here. */
export function EmployeeForm({
  initial,
  shiftNames,
  defaultExitPattern,
  dayCycles = [],
  onCancel,
  onSubmit,
}: {
  initial?: Record<string, unknown>;
  shiftNames: string[];
  defaultExitPattern: "round" | "triplet";
  dayCycles?: DayCycle[];
  onCancel: () => void;
  onSubmit: (employee: Record<string, unknown>) => void;
}) {
  const [name, setName] = useState(text(initial?.name));
  const [role, setRole] = useState(text(initial?.role));
  const [exitPattern, setExitPattern] = useState(
    text(initial?.exit_pattern) || defaultExitPattern,
  );
  const groups = patternGroups(exitPattern, dayCycles);
  // Daily hours and a personal 1-in-N, kept while the form is open.
  const [exitFields, setExitFields] = useState<Record<string, unknown>>(() => ({
    daily_days: Array.isArray(initial?.daily_days) ? initial.daily_days : [],
    daily_start: text(initial?.daily_start),
    daily_end: text(initial?.daily_end),
    closure_every: typeof initial?.closure_every === "number" ? initial.closure_every : null,
    closure_from: text(initial?.closure_from),
  }));
  const [rotationGroup, setRotationGroup] = useState(text(initial?.rotation_group) || groups[0] || "");
  // מעמד: the service type and, for a standard soldier, the rank, as one choice.
  const [status, setStatus] = useState(statusOf(text(initial?.service_type), text(initial?.rank_group)));
  const [countsTowardStaffing, setCountsTowardStaffing] = useState(initial?.counts_toward_staffing !== false);
  const [isShiftManager, setIsShiftManager] = useState(Boolean(initial?.is_shift_manager));
  const [canTrain, setCanTrain] = useState(Boolean(initial?.can_train));
  const [notes, setNotes] = useState(rawText(initial?.notes));
  const [competence, setCompetence] = useState(text(initial?.competence));
  const [reserveDays, setReserveDays] = useState<number | null>(
    typeof initial?.reserve_days_per_week === "number" ? initial.reserve_days_per_week : null,
  );
  const [reserveMinDays, setReserveMinDays] = useState<number | null>(
    typeof initial?.reserve_min_days === "number" ? initial.reserve_min_days : null,
  );
  const [reserveConsecutive, setReserveConsecutive] = useState(initial?.reserve_consecutive === true);
  const [reserveCall, setReserveCall] = useState(text(initial?.reserve_call));
  const initialEligible = Array.isArray(initial?.eligible_shifts)
    ? initial.eligible_shifts.filter((value): value is string => typeof value === "string")
    : shiftNames;
  const [eligible, setEligible] = useState<string[]>(initialEligible);

  return (
    <form className="constraint-form profile-form" onSubmit={(event) => {
      event.preventDefault();
      if (!name.trim()) return;
      onSubmit({ ...exitFields, name: name.trim(), role: role.trim(), eligible_shifts: eligible, exit_pattern: exitPattern, rotation_group: rotationGroup, ...statusFields(status), counts_toward_staffing: countsTowardStaffing, is_shift_manager: isShiftManager, can_train: canTrain, notes: notes.trim(), competence, reserve_days_per_week: reserveDays, reserve_min_days: reserveMinDays, reserve_consecutive: reserveConsecutive, reserve_call: reserveCall });
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
          setRotationGroup(patternGroups(pattern, dayCycles)[0] ?? "");
        }}>{Object.entries(EXIT_PATTERN_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          {dayCycles.map((cycle) => <option key={cycle.id} value={cyclePattern(cycle)}>{cycle.name} {cycle.groups.join(" / ")}</option>)}
          {isDayCycle(exitPattern) && !cycleOf(dayCycles, exitPattern) ? <option value={exitPattern}>מחזור שהוסר</option> : null}
        </select></label>
        {groups.length ? <label><span>קבוצה</span><select value={rotationGroup} onChange={(event) => setRotationGroup(event.target.value)}>{groups.map((group) => <option key={group}>{group}</option>)}</select></label> : null}
        <label><span>מעמד</span><select value={status} onChange={(event) => {
          setStatus(event.target.value);
          if (event.target.value === "overlap") setCountsTowardStaffing(false);
        }}>{Object.entries(STATUS_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      </div>
      <ExitPatternFields pattern={exitPattern} person={exitFields} onChange={(field, value) => setExitFields((current) => ({ ...current, [field]: value }))} />
      <SoldierFields
        serviceType={status}
        competence={competence}
        reserveDays={reserveDays}
        reserveMinDays={reserveMinDays}
        reserveConsecutive={reserveConsecutive}
        reserveCall={reserveCall}
        onChange={(field, value) => {
          if (field === "competence") setCompetence(String(value ?? ""));
          else if (field === "reserve_call") setReserveCall(String(value ?? ""));
          else if (field === "reserve_consecutive") setReserveConsecutive(value === true);
          else if (field === "reserve_min_days") setReserveMinDays(typeof value === "number" ? value : null);
          else setReserveDays(typeof value === "number" ? value : null);
        }}
      />
      <label className="profile-check"><input type="checkbox" checked={countsTowardStaffing} onChange={(event) => setCountsTowardStaffing(event.target.checked)} /><span>נספר/ת בתקן</span></label>
      <label className="profile-check"><input type="checkbox" checked={isShiftManager} onChange={(event) => setIsShiftManager(event.target.checked)} /><span>מוסמך/ת כמפקד/ת משמרת</span></label>
      <label className="profile-check"><input type="checkbox" checked={canTrain} onChange={(event) => setCanTrain(event.target.checked)} /><span>מוסמך/ת לחפוף</span></label>
      <label><span>הערות לחייל/ת</span><textarea value={notes} maxLength={200} rows={3} onChange={(event) => setNotes(event.target.value)} placeholder="מידע קבוע שכדאי לקחת בחשבון בשיבוץ" /></label>
      {shiftNames.length ? (
        <MultiSelect
          label="משמרות שהעובד/ת יכול/ה לבצע"
          values={shiftNames}
          selected={eligible}
          onChange={setEligible}
          placeholder="לא נבחרו משמרות"
        />
      ) : null}
      <FormActions onCancel={onCancel} ready={Boolean(name.trim())} />
    </form>
  );
}

/** The roster's add/edit form for one shift, shared with the changes tab
 *  ("הוספת משמרת"). */
export function ShiftForm({
  initial,
  onCancel,
  onSubmit,
  children,
}: {
  initial?: Record<string, unknown>;
  onCancel: () => void;
  onSubmit: (shift: Record<string, unknown>) => void;
  /** Extra fields shown above the buttons, saved by the caller. */
  children?: React.ReactNode;
}) {
  const [name, setName] = useState(text(initial?.name));
  const [start, setStart] = useState(text(initial?.start_time));
  const [end, setEnd] = useState(text(initial?.end_time));
  const [headcount, setHeadcount] = useState(shiftHeadcount(initial));
  const [onCall, setOnCall] = useState(Boolean(initial?.is_on_call));
  const [shiftType, setShiftType] = useState(text(initial?.shift_type) || (onCall ? "on_call" : "regular"));
  const [purpose, setPurpose] = useState(text(initial?.purpose));
  const [requiresManager, setRequiresManager] = useState(Boolean(initial?.requires_shift_manager));
  const [minLevel, setMinLevel] = useState(text(initial?.min_competence));
  const [startsOn, setStartsOn] = useState(text(initial?.starts_on));
  const [endsOn, setEndsOn] = useState(text(initial?.ends_on));
  const [temporary, setTemporary] = useState(Boolean(startsOn || endsOn));
  const ready = Boolean(name.trim()) && (!temporary || Boolean(startsOn && endsOn && startsOn <= endsOn));

  return (
    <form className="constraint-form profile-form" onSubmit={(event) => {
      event.preventDefault();
      if (!name.trim()) return;
      onSubmit({
        name: name.trim(), start_time: start, end_time: end,
        headcount, shift_type: shiftType, is_on_call: shiftType === "on_call", purpose,
        requires_shift_manager: requiresManager,
        min_competence: minLevel,
        starts_on: temporary ? startsOn : "",
        ends_on: temporary ? endsOn : "",
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
          <label><span>שעת התחלה</span><TimeInput value={start} onChange={setStart} /></label>
          <label><span>שעת סיום</span><TimeInput value={end} onChange={setEnd} /></label>
        </div>
        <small>אפשר להקליד שעה ישירות. סיום מוקדם מההתחלה מסמן משמרת שחוצה חצות.</small>
      </fieldset>
      <label><span>סוג משמרת</span><select value={shiftType} onChange={(event) => { setShiftType(event.target.value); setOnCall(event.target.value === "on_call"); }}><option value="regular">רגילה</option><option value="overlap">חפיפה</option><option value="on_call">כוננות</option></select></label>
      <label><span>ייעוד</span><input value={purpose} maxLength={120} onChange={(event) => setPurpose(event.target.value)} placeholder="סיור, חמ״ל, חפיפה…" /></label>
      <label><span>תקן בסיסי</span><input type="number" min={0} max={100} value={headcount} onChange={(event) => setHeadcount(Math.min(100, Math.max(0, Math.floor(Number(event.target.value)) || 0)))} />{headcount === 0 ? <small>תקן 0: המשמרת לא פועלת בימים האלה. תקן לסופ״ש נקבע במסך הגדרת היחידה.</small> : null}</label>
      <label>
        <span>משמרת חזקה — רמה מקצועית נדרשת</span>
        <ShiftLevelSelect value={minLevel} onChange={setMinLevel} />
        {minLevel ? <small>חיילים בדירוג נמוך יותר ישובצו כאן רק אם אין ברירה, והכרטיס שלהם יסומן.</small> : null}
      </label>
      <label className="profile-check"><input type="checkbox" checked={requiresManager} onChange={(event) => setRequiresManager(event.target.checked)} /><span>נדרש/ת מפקד/ת משמרת מוסמך/ת</span></label>
      <label className="profile-check"><input type="checkbox" checked={temporary} onChange={(event) => setTemporary(event.target.checked)} /><span>משמרת זמנית</span></label>
      {temporary ? (
        <fieldset className="profile-time-card">
          <legend>תקופת הפעילות</legend>
          <div className="constraint-time-grid">
            <label><span>מתאריך</span><DateInput value={startsOn} max={endsOn || undefined} required onChange={setStartsOn} /></label>
            <label><span>עד תאריך</span><DateInput value={endsOn} min={startsOn || undefined} required onChange={setEndsOn} /></label>
          </div>
          <small>המשמרת תופיע בלוח רק בתאריכים האלה, כולל יום ההתחלה והסיום.</small>
        </fieldset>
      ) : null}
      {children}
      <FormActions onCancel={onCancel} ready={ready} />
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
