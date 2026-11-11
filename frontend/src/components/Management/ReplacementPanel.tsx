"use client";

import { AlertTriangle, Check, LoaderCircle, Sparkles, UserRound } from "lucide-react";
import { Fragment, useEffect, useState } from "react";

import { DateInput, displayDate } from "@/components/DateInput";
import { ABSENCE_REASONS, absenceSentence, selectionSentence } from "@/lib/replacement";
import type { AbsenceReason } from "@/lib/replacement";
import { getReplacementOptions } from "@/services/api";
import type { ReplacementOptions } from "@/types";

const WEEKDAYS = ["ראשון", "שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת"];

/** The replacement tab: who is out, when, and who should cover.
 *
 *  Candidates appear as soon as a person and dates are chosen, in stages:
 *  the same role from the shift itself, then the same role from another
 *  place, then anyone else who fits — each under its own heading. Inside a
 *  stage they are ordered so the load spreads evenly — the server counts
 *  shifts and nights in the period, including the other covers in the same
 *  absence.
 *  Nothing here writes. "הכנת תוכנית" sends the choices to the agent as an
 *  ordinary message, which turns them into a plan in code (no model round)
 *  that waits for approval like every other change (D12).
 *
 *  Two filters can be set before the search: which shift type the cover
 *  should come from, and which role it should hold. They go to the server,
 *  which then checks only those people — a shorter list and a faster answer.
 *  The lists are the unit's own shift names and roles (`shiftNames`, `roles`). */
export function ReplacementPanel({ employees, shiftNames = [], roles = [], today, disabled, onPrepare }: {
  employees: string[];
  shiftNames?: string[];
  roles?: string[];
  today: string;
  disabled: boolean;
  onPrepare: (message: string) => void;
}) {
  const [employee, setEmployee] = useState("");
  const [reason, setReason] = useState<AbsenceReason>(ABSENCE_REASONS[0]);
  const [fromShift, setFromShift] = useState("");
  const [role, setRole] = useState("");
  const filtered = Boolean(fromShift || role);
  // Empty until the manager picks: the dates then default to `today`, which
  // may arrive after the tab first renders.
  const [fromPicked, setFrom] = useState("");
  const [toPicked, setTo] = useState("");
  const from = fromPicked || today;
  const to = toPicked && toPicked >= from ? toPicked : from;
  const [found, setFound] = useState<ReplacementOptions | null>(null);
  const [chosen, setChosen] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!employee || !from || !to || from > to) return;
    let cancelled = false;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      setLoading(true); setError("");
      getReplacementOptions(employee, from, to, {
        signal: controller.signal,
        fromShifts: fromShift ? [fromShift] : [],
        roles: role ? [role] : [],
      }).then((next) => {
        if (cancelled) return;
        setFound(next);
        setChosen(Object.fromEntries(next.slots.map((slot) => [slotKey(slot), slot.pick])));
      }).catch((reason) => {
        if (!cancelled) { setFound(null); setError(reason instanceof Error ? reason.message : "לא ניתן לחפש מחליפים"); }
      }).finally(() => { if (!cancelled) setLoading(false); });
    }, 250);
    return () => { cancelled = true; controller.abort(); clearTimeout(timer); };
  }, [employee, from, to, fromShift, role]);

  const prepare = () => {
    if (!found) return;
    const picks = found.slots.filter((slot) => chosen[slotKey(slot)])
      .map((slot) => selectionSentence(chosen[slotKey(slot)], slot.shift, slot.date, slot.replacing));
    onPrepare([absenceSentence(employee, reason, from, to), ...picks].join(" "));
  };

  return <section className="replacement-panel" aria-labelledby="replacement-title">
    <header>
      <h3 id="replacement-title">החלפת משמרת</h3>
      <p>בחרו מי לא זמין/ה ומתי. המחליפים מוצעים בהדרגה: קודם בעל/ת אותו תפקיד מהמשמרת, אחר כך אותו תפקיד ממקום אחר — ובכל שלב מי שהעומס עליו/ה הכי קל.</p>
    </header>
    <div className="replacement-fields">
      <label>מי<select value={employee} onChange={(event) => setEmployee(event.target.value)}>
        <option value="">בחירת עובד/ת…</option>
        {employees.map((name) => <option key={name} value={name}>{name}</option>)}
      </select></label>
      <label>סיבה (לא חובה)<select value={reason} onChange={(event) => setReason(event.target.value as AbsenceReason)}>
        {ABSENCE_REASONS.map((value) => <option key={value} value={value}>{value}</option>)}
      </select></label>
      <label>מתאריך<DateInput value={from} required onChange={setFrom} /></label>
      <label>עד תאריך<DateInput value={to} required min={from} onChange={setTo} /></label>
      {shiftNames.length ? <label>מחליף/ה מאיזו משמרת<select value={fromShift} onChange={(event) => setFromShift(event.target.value)}>
        <option value="">כל המשמרות</option>
        {shiftNames.map((name) => <option key={name} value={name}>{name}</option>)}
      </select></label> : null}
      {roles.length ? <label>בעל/ת תפקיד<select value={role} onChange={(event) => setRole(event.target.value)}>
        <option value="">כל התפקידים</option>
        {roles.map((name) => <option key={name} value={name}>{name}</option>)}
      </select></label> : null}
    </div>
    {loading ? <p className="replacement-status" role="status"><LoaderCircle size={15} /> בודק מי פנוי…</p> : null}
    {error ? <p className="replacement-error" role="alert">{error}</p> : null}
    {found?.error ? <p className="replacement-error" role="alert">{found.error}</p> : null}
    {employee && found && !found.error ? <>
      {!found.slots.length ? <p className="replacement-status">ל{employee} אין משמרות בטווח הזה. אפשר לשמור את ההיעדרות כדי שלא ישובץ/תשובץ בו.</p> : null}
      {found.slots.map((slot) => <ReplacementSlotCard key={slotKey(slot)} slot={slot}
        chosen={chosen[slotKey(slot)] ?? ""} disabled={disabled} filtered={filtered}
        onChoose={(name) => setChosen((previous) => ({ ...previous, [slotKey(slot)]: name }))} />)}
      {found.free_dates.length && found.slots.length ? <p className="replacement-status">
        בלי משמרות: {found.free_dates.map(dayLabel).join(", ")}. יישמר להם אילוץ היעדרות בלבד.</p> : null}
      <button type="button" className="replacement-prepare" disabled={disabled || loading} onClick={prepare}>
        <Sparkles size={15} /> הכנת תוכנית לאישור</button>
    </> : null}
  </section>;
}

export function ReplacementSlotCard({ slot, chosen, disabled, filtered = false, onChoose }: {
  slot: ReplacementOptions["slots"][number]; chosen: string; disabled: boolean;
  /** The search was narrowed by shift type or role: an empty list then means
   *  "nobody in this filter", and the plan still looks at everyone. */
  filtered?: boolean; onChoose: (name: string) => void;
}) {
  return <section className="conversation-candidates replacement-slot" aria-label={`מחליפים ל${slot.shift} ב${dayLabel(slot.date)}`}>
    <header><strong>{dayLabel(slot.date)} · {slot.shift}</strong>
      <span>{slot.start_time && slot.end_time ? `${slot.start_time}–${slot.end_time}` : ""}</span></header>
    {slot.candidates.length ? slot.candidates.map((candidate, index) => <Fragment key={candidate.employee}>
      <TierHeading label={candidate.tier_label} previous={slot.candidates[index - 1]?.tier_label} />
      <button type="button"
      aria-pressed={chosen === candidate.employee} disabled={disabled}
      className={chosen === candidate.employee ? "is-chosen" : undefined}
      onClick={() => onChoose(candidate.employee)}>
      <span className="candidate-avatar"><UserRound size={17} /></span>
      <span className="candidate-copy"><strong>{candidate.employee}
        {slot.pick === candidate.employee && slot.picked_by === "fairness" ? <em className="replacement-badge">הכי שווה</em> : null}</strong>
        <small>{candidate.why}</small>
        {candidate.requires_exception ? <small className="candidate-warning">
          <AlertTriangle size={13} aria-hidden="true" />
          {candidate.warnings?.map((warning) => warning.message).join(" · ") || "החלופה דורשת אישור חריגה בתוכנית."}
        </small> : null}</span>
      {chosen === candidate.employee ? <Check size={16} aria-hidden="true" /> : null}
    </button></Fragment>) : filtered
      ? <p>אין מחליף/ה מתאים/ה בסינון שנבחר. אפשר להרחיב את הסינון; בלי בחירה, התוכנית תציע את המתאים/ה ביותר מכלל הסגל.</p>
      : <p>{slot.why || "לא נמצא מחליף שעומד בכל הכללים."} המשמרת תישאר חסרה.</p>}
  </section>;
}

/** A stage's heading, once, where the stage begins. */
export function TierHeading({ label, previous }: { label?: string; previous?: string }) {
  return label && label !== previous ? <h4 className="replacement-tier">{label}</h4> : null;
}

function slotKey(slot: { date: string; shift: string }) {
  return `${slot.date}:${slot.shift}`;
}

function dayLabel(iso: string) {
  const day = new Date(`${iso}T00:00:00`).getDay();
  return `יום ${WEEKDAYS[day]} ${displayDate(iso)}`;
}
