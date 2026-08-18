"use client";

import { Check, HelpCircle, Send, Sparkles, X } from "lucide-react";
import { useEffect, useState } from "react";

import type { Proposal } from "@/types";

import { formatDate } from "./Calendar";

/** Talking to the agent about the schedule — the way changes actually happen.
 *
 *  The loop is deliberately two steps
 *  ([D8](../../../docs/DECISIONS.md#d8--two-reasons-both-required)):
 *
 *  1. The manager says what they want. The agent answers with a *proposal* —
 *     nothing has been written.
 *  2. The manager reads the agent's reasoning and confirms, or does not.
 *
 *  That gap is the product, not friction. Under
 *  [D3](../../../docs/DECISIONS.md#d3--the-agent-decides-code-only-audits-)
 *  the agent's judgment is final, so seeing *why* it picked this person is
 *  the manager's one cheap chance to catch a bad call — which is why the
 *  reasoning is rendered in full rather than tucked behind a disclosure. */
export function AgentChat({
  proposal,
  busy,
  draft,
  onPropose,
  onConfirm,
  onDismiss,
}: {
  proposal: Proposal | null;
  busy: boolean;
  /** A sentence the briefing offered, seeded into the composer.
   *
   *  Seeded, never sent: the manager still presses send, which is what keeps
   *  a suggestion a suggestion. An agent observation that dispatched itself
   *  would be the agent acting on its own conclusion — exactly what D15 is
   *  drawn to prevent. */
  draft?: string;
  onPropose: (request: string, reason?: string) => void;
  onConfirm: (reason: string) => void;
  onDismiss: () => void;
}) {
  const [request, setRequest] = useState("");
  const [reason, setReason] = useState("");

  // Keyed on the draft's own value so clicking the same suggestion twice
  // after editing the box puts it back, while the manager's typing is never
  // overwritten by a re-render carrying the same draft.
  useEffect(() => {
    if (draft) setRequest(draft);
  }, [draft]);

  const needsReason = proposal?.needs_reason ?? false;
  // The manager's reason: whatever they already stated, otherwise what they
  // are typing now in answer to the agent asking.
  const confirmReason = (proposal?.stated_reason || reason).trim();

  return (
    <section className="agent-chat" aria-label="שיחה עם הסוכן">
      <header className="agent-chat-header">
        <span className="brand-mark" aria-hidden="true">
          <Sparkles size={15} />
        </span>
        <div>
          <h3>שיחה על הסידור</h3>
          <p>אפשר לבקש שינוי, לשאול על השיבוץ, או לתכנן קדימה.</p>
        </div>
      </header>

      {proposal ? (
        <div className="proposal">
          <p className="proposal-reply">{proposal.reply}</p>

          {/* The agent asked why. No operations came back, and none will
              until it is answered — a missing reason is met with a question,
              never a rejection. */}
          {needsReason ? (
            <form
              className="proposal-reason"
              onSubmit={(event) => {
                event.preventDefault();
                if (!reason.trim()) return;
                onPropose(request || proposal.reply, reason.trim());
              }}
            >
              <label>
                <HelpCircle size={14} />
                <span>מה הסיבה לשינוי?</span>
                <input
                  type="text"
                  value={reason}
                  maxLength={200}
                  onChange={(event) => setReason(event.target.value)}
                  placeholder="מחלה, חופשה, בקשת העובד…"
                  autoFocus
                />
              </label>
              <button
                type="submit"
                className="primary-button"
                disabled={busy || !reason.trim()}
              >
                שליחה
              </button>
            </form>
          ) : null}

          {/* The agent's reasoning, shown before the manager confirms. This
              is the point of the confirmation step, not a detail. */}
          {proposal.agent_reason ? (
            <div className="proposal-reasoning">
              <span className="proposal-label">הנימוק של הסוכן</span>
              <p>{proposal.agent_reason}</p>
            </div>
          ) : null}

          {proposal.operations.length ? (
            <ul className="proposal-operations">
              {proposal.operations.map((operation, index) => (
                <li key={index}>
                  <span className={`op-badge op-${operation.action}`}>
                    {ACTION_LABELS[operation.action] ?? operation.action}
                  </span>
                  <span>
                    {operation.employee}
                    {operation.shift ? ` · ${operation.shift}` : ""}
                    {operation.date ? ` · ${formatDate(operation.date)}` : ""}
                    {operation.with_employee
                      ? ` ⇄ ${operation.with_employee}`
                      : ""}
                  </span>
                </li>
              ))}
            </ul>
          ) : null}

          {/* Warnings the change *would* produce, so a proposal that breaks
              something is visible before it is accepted rather than after.
              Still advisory: they do not disable the confirm button. */}
          {proposal.warnings.length ? (
            <ul className="proposal-warnings">
              {proposal.warnings.map((warning, index) => (
                <li key={index}>{warning.message}</li>
              ))}
            </ul>
          ) : null}

          <div className="proposal-actions">
            <button type="button" className="ghost-button" onClick={onDismiss}>
              <X size={14} />
              ביטול
            </button>
            {proposal.operations.length ? (
              <button
                type="button"
                className="primary-button"
                onClick={() => onConfirm(confirmReason)}
                disabled={busy || !confirmReason}
              >
                <Check size={14} />
                {busy ? "מחיל…" : "אישור השינוי"}
              </button>
            ) : null}
          </div>
        </div>
      ) : null}

      <form
        className="agent-composer"
        onSubmit={(event) => {
          event.preventDefault();
          const text = request.trim();
          if (!text || busy) return;
          onPropose(text);
          setRequest("");
          setReason("");
        }}
      >
        <input
          type="text"
          value={request}
          maxLength={500}
          onChange={(event) => setRequest(event.target.value)}
          placeholder="למשל: דנה חולה ביום חמישי"
          disabled={busy}
        />
        <button
          type="submit"
          className="primary-button"
          disabled={busy || !request.trim()}
          aria-label="שליחה"
        >
          <Send size={15} />
        </button>
      </form>
    </section>
  );
}

const ACTION_LABELS: Record<string, string> = {
  assign: "שיבוץ",
  remove: "הסרה",
  swap: "החלפה",
};
