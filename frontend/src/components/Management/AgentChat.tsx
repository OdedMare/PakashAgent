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

import { AgentAnswer as AgentAnswerBubble } from "./AgentAnswer";
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
  answer,
  answerBusy = false,
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
  onDismissAnswer,
}: {
  proposal: Proposal | null;
  answer: AgentAnswer | null;
  answerBusy?: boolean;
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
  onDismissAnswer: () => void;
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
  // The agent could not tell what the request referred to and asked. The
  // question is already in `reply`; what this changes is the composer, which
  // says "answer" rather than "request a change" — the manager is finishing
  // a sentence, not starting one.
  const needsInput = proposal?.needs_input ?? false;
  // The manager's reason: whatever they already stated, otherwise what they
  // are typing now in answer to the agent asking.
  const confirmReason = (proposal?.stated_reason || reason).trim();
  const hasScheduleOperations = Boolean(proposal?.operations.length);
  const hasProfileOperations = Boolean(proposal?.profile_operations.length);

  return (
    <section className="agent-chat" aria-label="שיחה עם הסוכן">
      <header className="agent-chat-header">
        <span className="brand-mark" aria-hidden="true">
          <Sparkles size={15} />
        </span>
        <div>
          <h3>שיחה עם הסוכן</h3>
          <p>
            {hasSchedule
              ? "אפשר להתייעץ על הצוות והסידור, או לבקש שינוי לאישור."
              : "אפשר להתייעץ על הצוות, להוסיף עובדים ולהגדיר משמרות."}
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
        <div className={needsInput ? "proposal proposal-asking" : "proposal"}>
          <p className="proposal-reply">
            {needsInput ? (
              <span className="proposal-question-mark" aria-hidden="true">
                <HelpCircle size={14} />
              </span>
            ) : null}
            {proposal.reply}
          </p>

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

          {proposal.profile_operations.length ? (
            <ul className="proposal-operations">
              {proposal.profile_operations.map((operation, index) => (
                <li key={`profile-${index}`}>
                  <span className="op-badge op-profile">
                    {PROFILE_ACTION_LABELS[operation.action] ?? operation.action}
                  </span>
                  <span>{profileOperationSummary(operation)}</span>
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
            {hasScheduleOperations || hasProfileOperations ? (
              <button
                type="button"
                className="primary-button"
                onClick={() => onConfirm(confirmReason)}
                disabled={
                  busy ||
                  (hasScheduleOperations && (writeLocked || !confirmReason))
                }
              >
                <Check size={14} />
                {busy ? "מחיל…" : "אישור השינוי"}
              </button>
            ) : null}
          </div>
        </div>
      ) : null}

      {answerBusy || answer ? (
        <div className="agent-answer-float">
          <AgentAnswerBubble
            answer={answer}
            busy={answerBusy}
            onDismiss={onDismissAnswer}
            onContinue={() =>
              document.getElementById("agent-composer-input")?.focus()
            }
          />
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
          id="agent-composer-input"
          type="text"
          value={request}
          maxLength={500}
          onChange={(event) => setRequest(event.target.value)}
          placeholder={
            needsInput
              ? "התשובה לשאלה של הסוכן — אין צורך לחזור על הבקשה"
              : hasSchedule
                ? "למשל: דנה חולה ביום חמישי"
                : "למשל: תוסיף את מאיה לצוות בתפקיד אחראית משמרת"
          }
          disabled={busy}
          autoFocus={needsInput}
        />
        {/* Asking and requesting are two buttons because they are two
            different acts. The magnifier reads the schedule and answers;
            send asks the agent to propose a change. Collapsing them would
            make every question produce a confirm button for something the
            manager did not ask for. */}
        {onAsk ? (
          <button
            type="button"
            className="ghost-button"
            onClick={() => {
              const text = request.trim();
              if (!text || busy) return;
              onAsk(text);
            }}
            disabled={busy || !request.trim()}
            aria-label="שאלה על הצוות או הסידור"
            title="שאלה — קריאה בלבד, בלי לשנות כלום"
          >
            <Search size={15} />
          </button>
        ) : null}
        <button
          type="submit"
          className="primary-button"
          disabled={busy || !request.trim()}
          aria-label="שליחה"
          title="בקשת שינוי — הסוכן יציע ואתם תאשרו"
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

const PROFILE_ACTION_LABELS: Record<string, string> = {
  add_employee: "הוספת עובד/ת",
  update_employee: "עריכת עובד/ת",
  add_shift: "הוספת משמרת",
  update_shift: "עריכת משמרת",
};

function profileOperationSummary(operation: Proposal["profile_operations"][number]): string {
  const name = String(operation.item.name ?? operation.target);
  if (operation.action.includes("employee")) {
    const role = String(operation.item.role ?? "").trim();
    return role ? `${name} · ${role}` : name;
  }
  const start = String(operation.item.start_time ?? "").trim();
  const end = String(operation.item.end_time ?? "").trim();
  const time = start || end ? ` · ${start || "—"}–${end || "—"}` : "";
  const headcount = Number(operation.item.headcount ?? 1);
  return `${name}${time} · תקן ${headcount}`;
}

const SCHEDULE_QUESTIONS = [
  "מי סוגר בסופ״ש הקרוב?",
  "מה חסר לפני פרסום?",
  "איפה יש חוסרים בסידור?",
] as const;

const PROFILE_QUESTIONS = [
  "מה עדיין חסר בפרופיל?",
  "מה כדאי להגדיר לפני הסידור הראשון?",
  "איזה טווח כדאי לבנות קודם?",
] as const;
