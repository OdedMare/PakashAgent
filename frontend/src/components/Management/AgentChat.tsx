"use client";

import {
  Check,
  FlaskConical,
  HelpCircle,
  Search,
  Send,
  Sparkles,
  X,
} from "lucide-react";
import { useState } from "react";

import type { AgentAnswer, Operation, Proposal, Simulation } from "@/types";

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
  hasSchedule = true,
  writeLocked = false,
  draft,
  draftKey,
  onPropose,
  onAsk,
  onSimulate,
  onConfirm,
  onDismiss,
}: {
  proposal: Proposal | null;
  busy: boolean;
  /** Without a period there is nothing to change, but the agent can still
   *  answer questions about the workplace and help decide what to build. */
  hasSchedule?: boolean;
  /** Published periods are read-only until the manager returns them to draft. */
  writeLocked?: boolean;
  /** A sentence the briefing offered, seeded into the composer.
   *
   *  Seeded, never sent: the manager still presses send, which is what keeps
   *  a suggestion a suggestion. An agent observation that dispatched itself
   *  would be the agent acting on its own conclusion — exactly what D15 is
   *  drawn to prevent. */
  draft?: string;
  /** Bumped each time a suggestion is clicked, so choosing the same one
   *  again re-seeds the box after the manager has edited it. Without it the
   *  effect below would not re-run on an identical `draft`. */
  draftKey?: number;
  onPropose: (request: string, reason?: string) => void;
  /** Ask about the schedule without asking for a change.
   *
   *  A separate verb because it is a separate act. "מי יכול להחליף את יוסי
   *  בשבת" is a question; answering it with a proposal would commit the
   *  manager to something they did not ask for, and the two-step contract
   *  exists precisely so a change is deliberate. */
  onAsk?: (request: string) => void;
  /** Turn the pending proposal into a simulation instead of applying it.
   *
   *  The manager reads the agent's reasoning and wants to see the
   *  consequences before committing. Nothing is written either way. */
  onSimulate?: (operations: Operation[]) => void;
  onConfirm: (reason: string) => void;
  onDismiss: () => void;
}) {
  const [request, setRequest] = useState("");
  const [reason, setReason] = useState("");

  // Adjusting state during render rather than in an effect: this is React's
  // own pattern for a value that resets when a prop changes, and it avoids
  // the cascading re-render an effect would cost.
  //
  // Keyed on `draftKey` rather than on the text, so clicking the same
  // suggestion again puts it back after the manager has edited the box —
  // while an ordinary re-render carrying the same draft never overwrites
  // what they are in the middle of typing.
  const [seeded, setSeeded] = useState(draftKey);
  if (draftKey !== seeded) {
    setSeeded(draftKey);
    if (draft) setRequest(draft);
  }

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
          <p>
            {hasSchedule
              ? "אפשר לבקש שינוי, לשאול על השיבוץ, או לתכנן קדימה."
              : "אפשר לדבר ולתכנן גם לפני שנבנה הסידור הראשון."}
          </p>
        </div>
      </header>

      {onAsk ? (
        <div className="agent-quick-questions" aria-label="שאלות מהירות">
          <span>אפשר לשאול</span>
          {(hasSchedule ? SCHEDULE_QUESTIONS : PROFILE_QUESTIONS).map((question) => (
            <button
              type="button"
              key={question}
              disabled={busy}
              onClick={() => onAsk(question)}
            >
              {question}
            </button>
          ))}
        </div>
      ) : null}

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
                if (!reason.trim() || writeLocked) return;
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
                disabled={busy || writeLocked || !reason.trim()}
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
            {/* See the consequences before committing to them. Writes
                nothing, exactly as the proposal itself has written nothing —
                this is a way to look harder, not a third path to a change. */}
            {proposal.operations.length && onSimulate ? (
              <button
                type="button"
                className="ghost-button"
                onClick={() => onSimulate(proposal.operations as Operation[])}
                disabled={busy}
                title="לראות מה השינוי היה עושה, בלי לבצע"
              >
                <FlaskConical size={14} />
                סימולציה
              </button>
            ) : null}
            {proposal.operations.length ? (
              <button
                type="button"
                className="primary-button"
                onClick={() => onConfirm(confirmReason)}
                disabled={busy || writeLocked || !confirmReason}
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
          if (!hasSchedule && onAsk) {
            onAsk(text);
            setRequest("");
            return;
          }
          if (writeLocked) return;
          onPropose(text);
          setRequest("");
          setReason("");
        }}
      >
        <input
          id="agent-composer-input"
          type="text"
          value={request}
          maxLength={500}
          onChange={(event) => setRequest(event.target.value)}
          placeholder={hasSchedule
            ? "למשל: דנה חולה ביום חמישי"
            : "למשל: מה כדאי להגדיר לפני שבונים סידור?"}
          disabled={busy}
        />
        {/* Asking and requesting are two buttons because they are two
            different acts. The magnifier reads the schedule and answers;
            send asks the agent to propose a change. Collapsing them would
            make every question produce a confirm button for something the
            manager did not ask for. */}
        {onAsk && hasSchedule ? (
          <button
            type="button"
            className="ghost-button"
            onClick={() => {
              const text = request.trim();
              if (!text || busy) return;
              onAsk(text);
            }}
            disabled={busy || !request.trim()}
            aria-label="שאלה על הסידור"
            title="שאלה — קריאה בלבד, בלי לשנות כלום"
          >
            <Search size={15} />
          </button>
        ) : null}
        <button
          type="submit"
          className="primary-button"
          disabled={busy || (hasSchedule && writeLocked) || !request.trim()}
          aria-label="שליחה"
          title={hasSchedule
            ? "בקשת שינוי — הסוכן יציע ואתם תאשרו"
            : "שליחת שאלה לסוכן"}
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

const SCHEDULE_QUESTIONS = [
  "מה חסר לפני פרסום?",
  "איפה יש חוסרים בסידור?",
  "איך נראה השבוע?",
] as const;

const PROFILE_QUESTIONS = [
  "מה עדיין חסר בפרופיל?",
  "מה כדאי להגדיר לפני הסידור הראשון?",
  "איזה טווח כדאי לבנות קודם?",
] as const;
