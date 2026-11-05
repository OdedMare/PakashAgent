"use client";

import { Check, UserRound } from "lucide-react";
import { Fragment } from "react";
import type { ManagerChatMessage, ManagerToolResult } from "@/types";
import { displayDate } from "@/components/DateInput";
import { selectionSentence } from "@/lib/replacement";
import { TierHeading } from "./ReplacementPanel";

/** Checked candidates per shift. Under a plan they are the alternatives:
 *  the plan's own pick is marked, and choosing another rebuilds the plan. */
export function ChatCandidates({ results, plan, disabled, onChoose }: {
  results: NonNullable<ManagerChatMessage["payload"]["results"]>;
  plan?: ManagerChatMessage["payload"]["plan"];
  disabled: boolean; onChoose: (request: string) => void;
}) {
  const planned = new Set((plan?.operations ?? []).filter((row) => row.action === "assign")
    .map((row) => `${row.date}:${row.shift}:${row.employee}`));
  const searches = new Map<string, ManagerToolResult>();
  for (const raw of results) if (raw.tool === "find_replacements" && raw.ok !== false) {
    const result = raw as ManagerToolResult;
    searches.set(`${result.date}:${result.shift}`, result);
  }
  return <>{[...searches].map(([key, result]) => {
    const candidates = (result.candidates ?? []).filter((row) => !row.requires_exception);
    return <section className="conversation-candidates" key={key} aria-label="מועמדים למשמרת">
      <header><strong>{result.shift}</strong><span>{result.date ? displayDate(result.date) : ""}</span></header>
      {candidates.length ? candidates.map((candidate, index) => {
        const inPlan = planned.has(`${result.date}:${result.shift}:${candidate.employee}`);
        return <Fragment key={candidate.employee}>
        <TierHeading label={candidate.tier_label} previous={candidates[index - 1]?.tier_label} />
        <button type="button" disabled={disabled || inPlan} aria-pressed={inPlan}
        onClick={() => onChoose(`${selectionSentence(candidate.employee, result.shift ?? "", result.date ?? "", result.replacing)} שמור את טווח ההיעדרות וכל הבחירות שכבר סיכמנו ובדוק את התוכנית המלאה לפני הצעתה לאישור.`)}>
        <span className="candidate-avatar"><UserRound size={17} /></span>
        <span className="candidate-copy"><strong>{candidate.employee}{inPlan ? <em className="replacement-badge">בתוכנית</em> : null}</strong>
          <small>{candidate.why ?? "מועמד מתאים לפי הבדיקות"}</small>
          {typeof candidate.hours === "number" && !candidate.why?.includes("שעות") ? <small>{candidate.hours} שעות משובצות בתקופה</small> : null}</span>
        <Check size={16} aria-hidden="true" />
      </button></Fragment>;
      }) : <p>לא נמצאו מועמדים שעומדים בכל הכללים. צריך לבחור דרך אחרת לפתרון החוסר.</p>}
    </section>;
  })}</>;
}
