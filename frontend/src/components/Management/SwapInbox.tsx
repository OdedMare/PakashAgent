"use client";

import { ArrowLeftRight, Check, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { approveSwap, pendingSwaps, rejectSwap } from "@/services/api";
import type { SwapRow } from "@/types";

/** Swaps two employees agreed to, waiting on the manager.
 *
 *  The manager's half of the swap feature. What arrives here has already
 *  cleared one gate the constraint inbox has no equivalent of: the *other*
 *  employee accepted. An offer nobody has taken up never appears — the
 *  manager rules on arrangements, not on proposals, and a list padded with
 *  half-made offers is a list that stops being read.
 *
 *  **A reason is required on both buttons here**, unlike `RequestInbox`
 *  where approving is one click. The difference is what the decision does: an
 *  approved constraint records a fact, while an approved swap *moves two
 *  assignments*, and [D8](../../../../docs/DECISIONS.md) does not exempt a
 *  change for having been suggested by the people it affects. The approve
 *  button stays disabled until there is a reason, so the requirement is
 *  visible rather than arriving as a server error afterwards.
 *
 *  `onDecided` re-reads the whole overview for the reason `RequestInbox`
 *  gives: an approval changes the grid, the fairness tally and the audit
 *  together, and a locally patched panel beside stale warnings is worse than
 *  a brief spinner. */
export function SwapInbox({
  onDecided,
  writeLocked = false,
}: {
  onDecided: () => void;
  writeLocked?: boolean;
}) {
  const [rows, setRows] = useState<SwapRow[]>([]);
  const [reasons, setReasons] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    pendingSwaps()
      .then(setRows)
      .catch(() => setRows([]));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const decide = async (row: SwapRow, approve: boolean) => {
    const reason = (reasons[row.id] ?? "").trim();
    if (!reason) return;
    setBusy(true);
    try {
      if (approve) await approveSwap(row.id, reason);
      else await rejectSwap(row.id, reason);
      load();
      onDecided();
    } catch {
      // Surfaced through the shared API logging. The row stays pending,
      // which is the honest state when a decision did not land.
    } finally {
      setBusy(false);
    }
  };

  // Nothing waiting renders nothing, as the constraint inbox does: this sits
  // in a busy sidebar and "no pending swaps" is not news worth a card.
  if (rows.length === 0) return null;

  return (
    <section className="management-panel request-inbox">
      <h2>
        <ArrowLeftRight size={15} /> בקשות החלפה
        <span className="inbox-count">{rows.length}</span>
      </h2>

      <ul className="request-list">
        {rows.map((row) => (
          <li key={row.id}>
            <div className="request-head">
              <strong>
                {row.requester} ⇄ {row.counterparty}
              </strong>
              <span className="request-date">
                {describeShift(row.requester_date, row.requester_shift)} ⇄{" "}
                {describeShift(
                  row.counterparty_date,
                  row.counterparty_shift,
                )}
              </span>
            </div>
            {/* That both agreed is the fact this inbox exists to carry: it is
                why the manager is being asked at all, and it is what makes
                this different from a constraint someone submitted alone. */}
            <p className="request-reason">
              שני העובדים הסכימו
              {row.reason ? ` — ${row.reason}` : ""}
            </p>
            <div className="request-actions">
              <input
                type="text"
                value={reasons[row.id] ?? ""}
                placeholder="סיבה (חובה)"
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
                // Disabled without a reason: approving here moves two
                // assignments, and the change log must not take one without
                // the manager's own sentence (D8).
                disabled={
                  busy || writeLocked || !(reasons[row.id] ?? "").trim()
                }
              >
                <Check size={13} /> אישור
              </button>
              <button
                type="button"
                className="reject"
                onClick={() => decide(row, false)}
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

function describeShift(iso: string, shift: string): string {
  const label = formatDate(iso);
  return shift ? `${label} · ${shift}` : label;
}

function formatDate(iso: string): string {
  const date = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(date.getTime())) return iso;
  return `${date.getDate()}.${date.getMonth() + 1}`;
}
