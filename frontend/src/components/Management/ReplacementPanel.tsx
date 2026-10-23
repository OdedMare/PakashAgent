"use client";

import { Check, LoaderCircle, Sparkles, UserRound } from "lucide-react";
import { useEffect, useState } from "react";

import { DateInput, displayDate } from "@/components/DateInput";
import { ABSENCE_REASONS, absenceSentence, selectionSentence } from "@/lib/replacement";
import type { AbsenceReason } from "@/lib/replacement";
import { getReplacementOptions } from "@/services/api";
import type { ReplacementOptions } from "@/types";

const WEEKDAYS = ["ראשון", "שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת"];

/** The replacement tab: who is out, when, and who should cover.
 *
 *  Candidates appear as soon as a person and dates are chosen, already
 *  ordered so the load spreads evenly — the server counts hours, shifts and
 *  nights in the period, including the other covers in the same absence.
 *  Nothing here writes. "הכנת תוכנית" sends the choices to the agent as an
 *  ordinary message, which turns them into a plan in code (no model round)
 *  that waits for approval like every other change (D12). */
export function ReplacementPanel({ employees, today, disabled, onPrepare }: {
  employees: string[];
  today: string;
  disabled: boolean;
  onPrepare: (message: string) => void;
}) {
  const [employee, setEmployee] = useState("");
  const [reason, setReason] = useState<AbsenceReason>("חולה");
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
    const timer = setTimeout(() => {
      setLoading(true); setError("");
      getReplacementOptions(employee, from, to).then((next) => {
        if (cancelled) return;
        setFound(next);
        setChosen(Object.fromEntries(next.slots.map((slot) => [slotKey(slot), slot.pick])));
      }).catch((reason) => {
        if (!cancelled) { setFound(null); setError(reason instanceof Error ? reason.message : "לא ניתן לחפש מחליפים"); }
      }).finally(() => { if (!cancelled) setLoading(false); });
    }, 250);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [employee, from, to]);

  const prepare = () => {
    if (!found) return;
    const picks = found.slots.filter((slot) => chosen[slotKey(slot)])
      .map((slot) => selectionSentence(chosen[slotKey(slot)], slot.shift, slot.date, slot.replacing));
    onPrepare([absenceSentence(employee, reason, from, to), ...picks].join(" "));
  };

  return <section className="replacement-panel" aria-labelledby="replacement-title">
    <header>
      <h2 id="replacement-title">החלפת עובד/ת</h2>
      <p>בחרו מי לא זמין/ה ומתי. המועמדים מסודרים כך שהעומס יתחלק הכי שווה.</p>
    </header>
    <div className="replacement-fields">
      <label>מי<select value={employee} onChange={(event) => setEmployee(event.target.value)}>
        <option value="">בחירת עובד/ת…</option>
        {employees.map((name) => <option key={name} value={name}>{name}</option>)}
      </select></label>
      <label>סיבה<select value={reason} onChange={(event) => setReason(event.target.value as AbsenceReason)}>
        {ABSENCE_REASONS.map((value) => <option key={value} value={value}>{value}</option>)}
      </select></label>
      <label>מתאריך<DateInput value={from} required onChange={setFrom} /></label>
      <label>עד תאריך<DateInput value={to} required min={from} onChange={setTo} /></label>
    </div>
    {loading ? <p className="replacement-status" role="status"><LoaderCircle size={15} /> בודק מי פנוי…</p> : null}
    {error ? <p className="replacement-error" role="alert">{error}</p> : null}
    {found?.error ? <p className="replacement-error" role="alert">{found.error}</p> : null}
    {employee && found && !found.error ? <>
      {!found.slots.length ? <p className="replacement-status">ל{employee} אין משמרות בטווח הזה. אפשר לשמור את ההיעדרות כדי שלא ישובץ/תשובץ בו.</p> : null}
      {found.slots.map((slot) => <ReplacementSlotCard key={slotKey(slot)} slot={slot}
        chosen={chosen[slotKey(slot)] ?? ""} disabled={disabled}
        onChoose={(name) => setChosen((previous) => ({ ...previous, [slotKey(slot)]: name }))} />)}
      {found.free_dates.length && found.slots.length ? <p className="replacement-status">
        בלי משמרות: {found.free_dates.map(dayLabel).join(", ")}. יישמר להם אילוץ היעדרות בלבד.</p> : null}
      <button type="button" className="replacement-prepare" disabled={disabled || loading} onClick={prepare}>
        <Sparkles size={15} /> הכנת תוכנית לאישור</button>
    </> : null}
  </section>;
}

function ReplacementSlotCard({ slot, chosen, disabled, onChoose }: {
  slot: ReplacementOptions["slots"][number]; chosen: string; disabled: boolean; onChoose: (name: string) => void;
}) {
  return <section className="conversation-candidates replacement-slot" aria-label={`מחליפים ל${slot.shift} ב${dayLabel(slot.date)}`}>
    <header><strong>{dayLabel(slot.date)} · {slot.shift}</strong>
      <span>{slot.start_time && slot.end_time ? `${slot.start_time}–${slot.end_time}` : ""}</span></header>
    {slot.candidates.length ? slot.candidates.map((candidate) => <button type="button" key={candidate.employee}
      aria-pressed={chosen === candidate.employee} disabled={disabled}
      className={chosen === candidate.employee ? "is-chosen" : undefined}
      onClick={() => onChoose(candidate.employee)}>
      <span className="candidate-avatar"><UserRound size={17} /></span>
      <span className="candidate-copy"><strong>{candidate.employee}
        {slot.pick === candidate.employee && slot.picked_by === "fairness" ? <em className="replacement-badge">הכי שווה</em> : null}</strong>
        <small>{candidate.why}</small></span>
      {chosen === candidate.employee ? <Check size={16} aria-hidden="true" /> : null}
    </button>) : <p>{slot.why || "לא נמצא מחליף שעומד בכל הכללים."} המשמרת תישאר חסרה.</p>}
  </section>;
}

function slotKey(slot: { date: string; shift: string }) {
  return `${slot.date}:${slot.shift}`;
}

function dayLabel(iso: string) {
  const day = new Date(`${iso}T00:00:00`).getDay();
  return `יום ${WEEKDAYS[day]} ${displayDate(iso)}`;
}
