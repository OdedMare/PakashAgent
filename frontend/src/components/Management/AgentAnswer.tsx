"use client";

import {
  CheckCircle2,
  CircleHelp,
  Cpu,
  Info,
  Search,
  Wrench,
} from "lucide-react";

import type { AgentAnswer as AgentAnswerRow } from "@/types";

/** What the agent found when the manager asked it something.
 *
 *  A fifth card state, distinct from the four that already exist on this
 *  screen — insight (`Briefing`), proposal awaiting approval (`AgentChat`),
 *  confirmed change (the grid itself), and error. This one is an **answer**:
 *  the agent read the schedule and is telling the manager what is there.
 *
 *  **It carries no operations, and there is no confirm button on it.** That
 *  is the whole difference from a proposal. The response type has no field
 *  an `apply` could read (the same property `Briefing` has, D15), so an
 *  answer is a sentence and stays one. When the answer describes something
 *  that *would* change the schedule, `needs_confirmation` says so plainly —
 *  and the manager acts on it by sending the change through the ordinary
 *  propose-then-confirm loop below.
 *
 *  **The steps are not debugging output.** They say which deterministic
 *  checks the answer rests on, and they are rendered because an answer whose
 *  checks are invisible has to be taken on faith — which is exactly what
 *  having `bl/tools.py` do the counting was meant to avoid
 *  ([D3](../../../docs/DECISIONS.md#d3--the-agent-decides-code-only-audits-)).
 *
 *  **`used_model: false` is stated, not hidden.** Without a model the agent
 *  answers a narrower set of questions, and a manager who cannot tell which
 *  mode they are in would read a "I did not understand" as the product being
 *  broken rather than as the model being unconfigured. */
export function AgentAnswer({
  answer,
  busy,
  onDismiss,
  onContinue,
}: {
  answer: AgentAnswerRow | null;
  busy: boolean;
  onDismiss: () => void;
  onContinue?: () => void;
}) {
  if (busy && !answer) {
    return (
      <section className="agent-answer is-busy" aria-live="polite">
        <Search size={15} />
        <span>בודק את הסידור…</span>
      </section>
    );
  }

  if (!answer) return null;

  return (
    <section
      className={`agent-answer${answer.understood ? "" : " is-unsure"}${answer.needs_input ? " needs-input" : ""}`}
      aria-label="תשובת הסוכן"
    >
      <header className="agent-answer-header">
        <span className="agent-answer-mark" aria-hidden="true">
          {answer.needs_input ? (
            <CircleHelp size={15} />
          ) : answer.understood ? (
            <CheckCircle2 size={15} />
          ) : (
            <CircleHelp size={15} />
          )}
        </span>
        <h3>
          {answer.needs_input
            ? "שאלת המשך"
            : answer.understood ? "מה שמצאתי" : "לא הבנתי את הבקשה"}
        </h3>
        <button
          type="button"
          className="agent-answer-close"
          onClick={onDismiss}
          aria-label="סגירה"
        >
          ×
        </button>
      </header>

      {/* Newline-separated: the deterministic answers are built as lists of
          Hebrew lines and collapsing them into one paragraph would lose the
          per-shift structure that makes them readable. */}
      <div className="agent-answer-body">
        {answer.answer.split("\n").map((line, index) => (
          <p key={index}>{line}</p>
        ))}
      </div>

      {answer.needs_input && onContinue ? (
        <button
          type="button"
          className="agent-answer-continue"
          onClick={onContinue}
        >
          כתיבת תשובה
        </button>
      ) : null}

      {/* Nothing has happened. Said outright rather than implied by the
          absence of a confirm button (D8/D12). */}
      {answer.needs_confirmation ? (
        <p className="agent-answer-note">
          <Info size={13} />
          <span>
            עוד לא השתנה כלום. כדי לבצע — שלחו את הבקשה בשיחה למטה ואשרו עם
            סיבה.
          </span>
        </p>
      ) : null}

      {answer.steps.length ? (
        <details className="agent-answer-steps">
          <summary>
            <Wrench size={12} />
            <span>מה נבדק ({answer.steps.length})</span>
          </summary>
          <ul>
            {answer.steps.map((step, index) => (
              <li key={index} className={step.ok ? "" : "is-failed"}>
                {TOOL_LABELS[step.tool] ?? step.tool}
              </li>
            ))}
          </ul>
        </details>
      ) : null}

      {!answer.used_model ? (
        <p className="agent-answer-mode">
          <Cpu size={12} />
          <span>נענה בלי מודל — חישוב ישיר מהסידור.</span>
        </p>
      ) : null}
    </section>
  );
}

/** The tools in the manager's language.
 *
 *  Mirrors `TOOL_DESCRIPTIONS` in `bl/tools.py`, which is also what the
 *  model is handed as its menu — so what the agent was offered and what the
 *  manager is told it ran are the same words. */
const TOOL_LABELS: Record<string, string> = {
  read_period: "קריאת הסידור",
  employee_state: "המשמרות והשעות של העובד/ת",
  coverage_gaps: "איתור משמרות חסרות",
  validate_placement: "בדיקת תקינות שיבוץ",
  find_replacements: "חיפוש מחליפים",
  publish_readiness: "בדיקה לפני פרסום",
  profile_gaps: "מה עוד חסר לסוכן על מקום העבודה",
};
