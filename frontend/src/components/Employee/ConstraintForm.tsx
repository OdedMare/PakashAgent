"use client";

import { CalendarPlus, Check, Clock3, X } from "lucide-react";
import { useState } from "react";

import { RequestCalendar } from "./RequestCalendar";
import { adjacentDateLabel, requestPeriodLabel } from "../dateFormat";
import { DateInput } from "@/components/DateInput";
import type { ConstraintRequestPeriod, ConstraintRequestRow } from "@/types";

/** Ask not to be scheduled — and see what happened to previous asks.
 *
 *  **This submits a request, not a constraint.** Nothing about the schedule
 *  changes when it is sent: the row lands as `pending`, is invisible to
 *  `bl/audit.py`, and only the manager's approval turns it into a real
 *  constraint ([D14](../../../../docs/DECISIONS.md)). The copy says so
 *  plainly, because an employee who believes a submitted constraint is
 *  already in force is the failure mode this feature would otherwise
 *  introduce.
 *
 *  Shift is optional: empty means the whole day, read exactly as
 *  `availability.shift_name` is. */
export function ConstraintForm({
  initial,
  shiftNames,
  requests,
  busy,
  onSubmit,
  onWithdraw,
}: {
  initial?: { date: string; shift: string };
  shiftNames: string[];
  requests: ConstraintRequestRow[];
  busy: boolean;
  onSubmit: (body: ConstraintRequestPeriod & {
    shift_name?: string;
    available?: boolean;
    reason?: string;
  }) => Promise<boolean>;
  onWithdraw: (requestId: string) => void;
}) {
  const [date, setDate] = useState(initial?.date || "");
  const [end, setEnd] = useState("");
  const [before, setBefore] = useState("");
  const [after, setAfter] = useState("");
  const [shift, setShift] = useState(initial?.shift || "");
  const [reason, setReason] = useState("");
  // "I can work this" is the rarer case but a real one, and a manager wants
  // it: an offer to cover is information the schedule can use.
  const [available, setAvailable] = useState(false);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!date) return;
    const sent = await onSubmit({
      constraint_date: date,
      end_date: end || date,
      before_shift: available ? "" : before,
      after_shift: available ? "" : after,
      shift_name: shift,
      available,
      reason,
    });
    if (sent) {
      setDate("");
      setEnd("");
      setBefore("");
      setAfter("");
      setShift("");
      setReason("");
      setAvailable(false);
    }
  };

  return (
    <section className="employee-panel">
      <h2>
        <CalendarPlus size={15} /> בקשת אילוץ
      </h2>
      <p className="employee-note">
        רק אתם ומנהל הצוות רואים את הבקשה ואת הסיבה שכתבתם. עד שהמנהל יאשר אותה היא לא משנה את הסידור.
      </p>

      <RequestCalendar start={date} end={end} disabled={busy}
        onSelect={(first, last) => { setDate(first); setEnd(last); }} />
      <form className="employee-constraint-form" onSubmit={submit}>
        <label htmlFor="constraint-date">תאריך התחלה</label>
        <DateInput
          id="constraint-date"
          value={date}
          onChange={setDate}
          disabled={busy}
          required
        />

        <label htmlFor="constraint-end">עד תאריך (כולל)</label>
        <input id="constraint-end" type="date" min={date} value={end} disabled={busy}
          onChange={(event) => setEnd(event.target.value)} />

        <label htmlFor="constraint-shift">משמרת</label>
        <select
          id="constraint-shift"
          value={shift}
          onChange={(event) => setShift(event.target.value)}
          disabled={busy}
        >
          {/* Empty is the whole day — the default, and the common case. */}
          <option value="">כל היום</option>
          {Array.from(new Set([...shiftNames, ...(initial?.shift ? [initial.shift] : [])])).map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </select>

        <label htmlFor="constraint-reason">סיבה</label>
        <textarea
          id="constraint-reason"
          value={reason}
          rows={2}
          placeholder="למשל: אירוע משפחתי, בחינה"
          onChange={(event) => setReason(event.target.value)}
          disabled={busy}
        />

        <label className="constraint-toggle">
          <input
            type="checkbox"
            checked={available}
            onChange={(event) => setAvailable(event.target.checked)}
            disabled={busy}
          />
          <span>אני דווקא כן יכול/ה לעבוד אז</span>
        </label>

        {!available && shiftNames.length > 0 && [
          { label: "חסימת משמרת ביום שלפני התקופה", day: adjacentDateLabel(date, -1), value: before, change: setBefore },
          { label: "חסימת משמרת ביום שאחרי התקופה", day: adjacentDateLabel(end || date, 1), value: after, change: setAfter },
        ].map(({ label, day, value, change }) => (
          <label className="request-edge" key={label}>{label}{day && ` · ${day}`}
            <select value={value} disabled={busy} onChange={(event) => change(event.target.value)}>
              <option value="">ללא חסימה נוספת</option>
              {shiftNames.map(name => <option key={name} value={name}>{name}</option>)}
            </select>
          </label>
        ))}
        <button type="submit" disabled={!date || busy}>
          שליחה לאישור
        </button>
      </form>

      {requests.length > 0 ? (
        <div className="request-list">
          <h3>הבקשות שלי</h3>
          <ul>
            {requests.map((row) => (
              <li key={row.id} className={`request ${row.status}`}>
                <div className="request-head">
                  <StatusBadge status={row.status} />
                  <span className="request-date">
                    {requestPeriodLabel(row)}
                  </span>
                </div>
                {row.reason ? (
                  <p className="request-reason">{row.reason}</p>
                ) : null}
                {/* The manager's answer. Required on a rejection — a refusal
                    that says nothing is how this channel stops being used. */}
                {row.decided_reason ? (
                  <p className="request-decision">
                    תשובת המנהל: {row.decided_reason}
                  </p>
                ) : null}
                {row.status === "pending" ? (
                  <button
                    type="button"
                    className="request-withdraw"
                    onClick={() => onWithdraw(row.id)}
                    disabled={busy}
                  >
                    ביטול הבקשה
                  </button>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}

function StatusBadge({ status }: { status: ConstraintRequestRow["status"] }) {
  if (status === "approved") {
    return (
      <span className="status approved">
        <Check size={12} /> אושרה
      </span>
    );
  }
  if (status === "rejected") {
    return (
      <span className="status rejected">
        <X size={12} /> נדחתה
      </span>
    );
  }
  if (status === "withdrawn") {
    return <span className="status withdrawn">בוטלה</span>;
  }
  return (
    <span className="status pending">
      <Clock3 size={12} /> ממתינה לאישור
    </span>
  );
}
