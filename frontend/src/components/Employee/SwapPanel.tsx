"use client";

import { ArrowLeftRight, Check, X } from "lucide-react";
import { useState } from "react";

import type { EmployeeView, SwapRow } from "@/types";

/** Swaps: offering one, answering one, and watching what happened to it.
 *
 *  The second thing an employee may write, and the same kind of thing as the
 *  first ([D14](../../../../docs/DECISIONS.md)): a **request**. Offering
 *  moves nothing, and neither does the colleague accepting — acceptance only
 *  puts the swap in the manager's inbox, because the manager remains the
 *  sole decider of what the schedule says.
 *
 *  The panel says that outright rather than implying it. A screen where two
 *  people click "accept" and the grid does not change is confusing unless it
 *  states, at the moment of the click, that a third person still has to
 *  agree.
 *
 *  Both halves of the offer are picked from shifts already on screen: the
 *  employee's own, and a colleague's from the same published schedule. That
 *  is why the form takes assignment ids — a date-and-shift pair could name a
 *  slot that does not exist, and the server would have to guess what was
 *  meant. */
export function SwapPanel({
  view,
  busy,
  onOffer,
  onAnswer,
  onCancel,
}: {
  view: EmployeeView;
  busy: boolean;
  onOffer: (body: {
    assignment_id: string;
    counterparty: string;
    counterparty_assignment_id: string;
    reason?: string;
  }) => Promise<boolean>;
  onAnswer: (swapId: string, agreed: boolean) => void;
  onCancel: (swapId: string) => void;
}) {
  const swaps = view.swaps ?? [];
  const incoming = swaps.filter(
    (row) => row.is_counterparty && row.status === "awaiting_counterparty",
  );
  // Everything else worth showing: what this person offered, and what has
  // since been decided. Settled rows stay visible because the manager's
  // reason on a refusal is the part the employee actually needs to read.
  const rest = swaps.filter((row) => !incoming.includes(row));

  return (
    <section className="employee-panel swap-panel">
      <h2>
        <ArrowLeftRight size={15} /> החלפות משמרות
        {incoming.length > 0 ? (
          <span className="change-badge">{incoming.length} ממתינות לך</span>
        ) : null}
      </h2>

      {incoming.length > 0 ? (
        <ul className="swap-list swap-incoming">
          {incoming.map((row) => (
            <li key={row.id}>
              <p className="swap-offer">
                <strong>{row.requester}</strong> מציע/ה לך את{" "}
                {describeShift(row.requester_date, row.requester_shift)}{" "}
                בתמורה ל{describeShift(
                  row.counterparty_date,
                  row.counterparty_shift,
                )}{" "}
                שלך.
              </p>
              {row.reason ? (
                <p className="swap-reason">הסיבה: {row.reason}</p>
              ) : null}
              <p className="swap-note">
                אם תאשר/י, הבקשה תעבור לאישור המנהל. הסידור לא משתנה עד אז.
              </p>
              <div className="swap-actions">
                <button
                  type="button"
                  className="approve"
                  onClick={() => onAnswer(row.id, true)}
                  disabled={busy}
                >
                  <Check size={13} /> מסכים/ה
                </button>
                <button
                  type="button"
                  className="reject"
                  onClick={() => onAnswer(row.id, false)}
                  disabled={busy}
                >
                  <X size={13} /> לא מתאים לי
                </button>
              </div>
            </li>
          ))}
        </ul>
      ) : null}

      <OfferForm view={view} busy={busy} onOffer={onOffer} />

      {rest.length > 0 ? (
        <ul className="swap-list swap-history">
          {rest.map((row) => (
            <li key={row.id}>
              <span className="swap-when">
                {describeShift(row.requester_date, row.requester_shift)} ⇄{" "}
                {describeShift(row.counterparty_date, row.counterparty_shift)}
              </span>
              <span className="swap-who">
                {row.is_requester
                  ? `עם ${row.counterparty}`
                  : `מ${row.requester}`}
              </span>
              <span className={`swap-status is-${row.status}`}>
                {statusLabel(row)}
              </span>
              {row.decided_reason ? (
                <span className="swap-reason">{row.decided_reason}</span>
              ) : null}
              {/* Withdrawing stays available right up until the manager
                  rules: the shift is still this person's until the swap
                  actually happens, so a change of plans should not need the
                  manager to undo something that never landed. */}
              {row.is_requester &&
              (row.status === "awaiting_counterparty" ||
                row.status === "pending") ? (
                <button
                  type="button"
                  className="ghost-button"
                  onClick={() => onCancel(row.id)}
                  disabled={busy}
                >
                  ביטול
                </button>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

/** Pick one of my shifts, one of theirs, and say why.
 *
 *  The colleague list is derived from the schedule rather than the roster:
 *  only somebody who actually has a shift in this period has anything to
 *  trade, and offering a swap to a person who is not working is a request
 *  the server would refuse anyway. */
function OfferForm({
  view,
  busy,
  onOffer,
}: {
  view: EmployeeView;
  busy: boolean;
  onOffer: (body: {
    assignment_id: string;
    counterparty: string;
    counterparty_assignment_id: string;
    reason?: string;
  }) => Promise<boolean>;
}) {
  const [mine, setMine] = useState("");
  const [theirs, setTheirs] = useState("");
  const [reason, setReason] = useState("");

  const assignments = view.schedule?.assignments ?? [];
  const ownShifts = assignments.filter(
    (row) => row.employee === view.employee,
  );
  const otherShifts = assignments.filter(
    (row) => row.employee !== view.employee,
  );

  if (ownShifts.length === 0 || otherShifts.length === 0) return null;

  const chosen = otherShifts.find((row) => row.id === theirs);

  const submit = async () => {
    if (!mine || !chosen) return;
    const done = await onOffer({
      assignment_id: mine,
      counterparty: chosen.employee,
      counterparty_assignment_id: chosen.id,
      reason: reason.trim(),
    });
    if (done) {
      setMine("");
      setTheirs("");
      setReason("");
    }
  };

  return (
    <div className="swap-form">
      <label>
        המשמרת שלי
        <select
          value={mine}
          onChange={(event) => setMine(event.target.value)}
          disabled={busy}
        >
          <option value="">בחר/י משמרת</option>
          {ownShifts.map((row) => (
            <option key={row.id} value={row.id}>
              {describeShift(row.date, row.shift)}
            </option>
          ))}
        </select>
      </label>

      <label>
        בתמורה ל
        <select
          value={theirs}
          onChange={(event) => setTheirs(event.target.value)}
          disabled={busy}
        >
          <option value="">בחר/י משמרת של עובד אחר</option>
          {otherShifts.map((row) => (
            <option key={row.id} value={row.id}>
              {row.employee} · {describeShift(row.date, row.shift)}
            </option>
          ))}
        </select>
      </label>

      <label>
        סיבה
        <input
          type="text"
          value={reason}
          placeholder="למשל: חתונה של אחותי"
          onChange={(event) => setReason(event.target.value)}
          disabled={busy}
        />
      </label>

      <p className="swap-note">
        הבקשה נשלחת קודם לעובד/ת שבחרת, ורק אחרי שהוא/היא מסכים/ה היא עוברת
        לאישור המנהל. שום דבר בסידור לא משתנה לפני כן.
      </p>

      <button
        type="button"
        className="primary-button"
        onClick={() => void submit()}
        disabled={busy || !mine || !theirs}
      >
        <ArrowLeftRight size={14} /> שליחת בקשה
      </button>
    </div>
  );
}

/** What a swap's status means to the person reading it.
 *
 *  `declined` and `rejected` are deliberately worded differently: which of
 *  the two people said no decides whether it is worth asking somebody else,
 *  and a single "נדחתה" for both would throw that away. */
function statusLabel(row: SwapRow): string {
  switch (row.status) {
    case "awaiting_counterparty":
      return row.is_requester ? "ממתינה לתשובה" : "ממתינה לתשובתך";
    case "pending":
      return "ממתינה לאישור המנהל";
    case "approved":
      return "אושרה";
    case "rejected":
      return "המנהל דחה";
    case "declined":
      return "לא הסתדר בין העובדים";
    case "withdrawn":
      return "בוטלה";
    default:
      return row.status;
  }
}

function describeShift(iso: string, shift: string): string {
  const label = formatDate(iso);
  return shift ? `${label} · ${shift}` : label;
}

function formatDate(iso: string): string {
  const date = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(date.getTime())) return iso;
  return `${String(date.getDate()).padStart(2, "0")}/${String(date.getMonth() + 1).padStart(2, "0")}`;
}
