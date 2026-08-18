"use client";

import { Check, Inbox, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import {
  approveRequest,
  pendingRequests,
  rejectRequest,
} from "@/services/api";
import type { ConstraintRequestRow } from "@/types";

/** Constraint requests waiting on the manager.
 *
 *  The manager's half of [D14](../../../../docs/DECISIONS.md). Employees may
 *  now submit, but a submission is inert until it is ruled on here — the
 *  approval is what writes the `availability` row and therefore the moment
 *  the request starts counting in `bl/audit.py`.
 *
 *  Approving is one click; rejecting requires a reason, and the button stays
 *  disabled until there is one. That mirrors `ConfirmMove`: the requirement is
 *  visible in the UI rather than arriving as a server error afterwards, and
 *  the reason is captured at the only moment it is cheap — while the manager
 *  still has it in mind ([D8](../../../../docs/DECISIONS.md)).
 *
 *  `onDecided` re-reads the whole overview rather than patching locally: an
 *  approval changes the constraints *and* the audit, and a locally patched
 *  panel beside a stale set of warnings is worse than a brief spinner. */
export function RequestInbox({ onDecided }: { onDecided: () => void }) {
  const [rows, setRows] = useState<ConstraintRequestRow[]>([]);
  const [reasons, setReasons] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    pendingRequests()
      .then(setRows)
      .catch(() => setRows([]));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const decide = async (
    row: ConstraintRequestRow,
    approve: boolean,
  ) => {
    setBusy(true);
    try {
      if (approve) await approveRequest(row.id, reasons[row.id] ?? "");
      else await rejectRequest(row.id, reasons[row.id] ?? "");
      load();
      onDecided();
    } catch {
      // The error surfaces through the shared API logging; the row simply
      // stays pending, which is the honest state when a decision did not land.
    } finally {
      setBusy(false);
    }
  };

  // An empty inbox renders nothing rather than an empty-state card. This sits
  // in a busy sidebar, and "no pending requests" is not news the manager needs
  // to be told on every visit.
  if (rows.length === 0) return null;

  return (
    <section className="management-panel request-inbox">
      <h2>
        <Inbox size={15} /> בקשות אילוץ
        <span className="inbox-count">{rows.length}</span>
      </h2>

      <ul className="request-list">
        {rows.map((row) => (
          <li key={row.id}>
            <div className="request-head">
              <strong>{row.employee}</strong>
              <span className="request-date">
                {formatDate(row.constraint_date)}
                {row.shift_name ? ` · ${row.shift_name}` : " · כל היום"}
              </span>
            </div>
            {/* `available` inverts the meaning: an offer to work, not a
                request to be left out. Both are useful to a manager. */}
            <p className="request-reason">
              {row.available ? "מבקש/ת לעבוד" : "מבקש/ת לא לעבוד"}
              {row.reason ? ` — ${row.reason}` : ""}
            </p>
            <div className="request-actions">
              <input
                type="text"
                value={reasons[row.id] ?? ""}
                placeholder="סיבה (חובה לדחייה)"
                onChange={(event) =>
                  setReasons((current) => ({
                    ...current,
                    [row.id]: event.target.value,
                  }))
                }
                disabled={busy}
              />
              <button
                type="button"
                className="approve"
                onClick={() => decide(row, true)}
                disabled={busy}
              >
                <Check size={13} /> אישור
              </button>
              <button
                type="button"
                className="reject"
                onClick={() => decide(row, false)}
                // Disabled without a reason, so the requirement is visible
                // rather than enforced by a 502 after the click.
                disabled={busy || !(reasons[row.id] ?? "").trim()}
              >
                <X size={13} /> דחייה
              </button>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

function formatDate(iso: string): string {
  const date = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(date.getTime())) return iso;
  return `${date.getDate()}.${date.getMonth() + 1}`;
}
