"use client";

import { Check, UserRound } from "lucide-react";
import type { ManagerChatMessage } from "@/types";
import { displayDate } from "@/components/DateInput";

export function ChatCandidates({ results, disabled, onChoose }: {
  results: NonNullable<ManagerChatMessage["payload"]["results"]>;
  disabled: boolean; onChoose: (request: string) => void;
}) {
  const searches = new Map<string, typeof results[number]>();
  for (const result of results) if (result.tool === "find_replacements" && result.ok !== false)
    searches.set(`${result.date}:${result.shift}`, result);
  return <>{[...searches].map(([key, result]) => {
    const candidates = (result.candidates ?? []).filter((row) => !row.requires_exception);
    return <section className="conversation-candidates" key={key} aria-label="מועמדים למשמרת">
      <header><strong>{result.shift}</strong><span>{result.date ? displayDate(result.date) : ""}</span></header>
      {candidates.length ? candidates.map((candidate) => <button type="button" key={candidate.employee} disabled={disabled}
        onClick={() => onChoose(`אני בוחר את ${candidate.employee} למשמרת ${result.shift} בתאריך ${result.date}${result.replacing ? ` במקום ${result.replacing}` : ""}. שמור את טווח ההיעדרות וכל הבחירות שכבר סיכמנו ובדוק את התוכנית המלאה לפני הצעתה לאישור.`)}>
        <span className="candidate-avatar"><UserRound size={17} /></span>
        <span className="candidate-copy"><strong>{candidate.employee}</strong><small>{candidate.why ?? "מועמד מתאים לפי הבדיקות"}</small>
          {typeof candidate.hours === "number" ? <small>{candidate.hours} שעות משובצות בתקופה</small> : null}</span>
        <Check size={16} aria-hidden="true" />
      </button>) : <p>לא נמצאו מועמדים שעומדים בכל הכללים. צריך לבחור דרך אחרת לפתרון החוסר.</p>}
    </section>;
  })}</>;
}
