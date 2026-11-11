"use client";

import { Inbox, X } from "lucide-react";
import { useEffect } from "react";

import { shortDate } from "@/components/DateInput";
import type { ConstraintRequestRow } from "@/types";

/** The pop-up that says an employee just submitted a constraint.
 *
 *  It announces; it decides nothing. The only action is opening the request
 *  inbox, where approving and rejecting already live (D14) — a pop-up with its
 *  own approve button would be a second, reason-less way to rule on a request.
 *
 *  It leaves on its own after a while, because the badge on the "בקשות" tab
 *  keeps the count either way: missing the pop-up loses nothing. */
export function RequestToast({
  arrivals,
  onOpen,
  onDismiss,
}: {
  arrivals: ConstraintRequestRow[];
  onOpen: () => void;
  onDismiss: () => void;
}) {
  const latest = arrivals[arrivals.length - 1];

  // Restarted by every new arrival, so a second submission is not cut short
  // by the first one's timer.
  useEffect(() => {
    if (!latest) return;
    const timer = window.setTimeout(onDismiss, 12000);
    return () => window.clearTimeout(timer);
  }, [latest, onDismiss]);

  if (!latest) return null;
  const more = arrivals.length - 1;

  return (
    <div className="request-toast" role="status" aria-live="polite">
      <span className="request-toast-icon" aria-hidden="true">
        <Inbox size={17} />
      </span>
      <div className="request-toast-body">
        <strong>
          {more > 0
            ? `${arrivals.length} אילוצים חדשים ממתינים לאישור`
            : `${latest.employee} שלח/ה אילוץ חדש`}
        </strong>
        <span>
          {more > 0
            ? `האחרון: ${latest.employee} · ${shortDate(latest.constraint_date)}`
            : `${shortDate(latest.constraint_date)} · ${latest.shift_name || "כל היום"} · ${latest.available ? "מבקש/ת לעבוד" : "מבקש/ת לא לעבוד"}`}
        </span>
      </div>
      <button type="button" className="request-toast-open" onClick={onOpen}>
        לצפייה
      </button>
      <button
        type="button"
        className="icon-button request-toast-close"
        onClick={onDismiss}
        aria-label="סגירת ההתראה"
      >
        <X size={15} />
      </button>
    </div>
  );
}
