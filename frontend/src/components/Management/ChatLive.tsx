"use client";

import { LoaderCircle, Sparkles, X } from "lucide-react";
import { Markdown } from "@/components/Markdown";

/** A turn still being answered: the reply as it is written, or, before the
 *  first words arrive, what the agent is checking right now. The server saves
 *  both on the working message and signals each change. */
export function Thinking({ steps, activity, draft }: { steps: { tool: string; ok: boolean }[]; activity?: string; draft?: string }) {
  const current = steps.length ? ACTIVE_LABELS[steps[steps.length - 1].tool] ?? "בודק את הסידור" : "";
  const status = activity || (current ? `${current}…` : "רגע, קורא את הבקשה…");
  return <>
    {draft ? <div className="conversation-draft" aria-busy="true"><Markdown text={draft} /></div> : null}
    <div className="conversation-thinking" role="status"><LoaderCircle size={16} />
      <span>{draft ? "ממשיך לכתוב…" : status}
        {steps.length > 1 ? <small> · {steps.length} בדיקות עד עכשיו</small> : null}</span></div>
  </>;
}

/** Next messages the agent offers; a click sends one as the manager's own. */
export function Suggestions({ values, disabled, onChoose }: { values: string[]; disabled: boolean; onChoose: (value: string) => void }) {
  if (!values.length) return null;
  return <div className="conversation-suggestions" aria-label="הצעות להמשך">
    {values.map((value) => <button type="button" key={value} disabled={disabled} onClick={() => onChoose(value)}>
      <Sparkles size={12} aria-hidden="true" />{value}</button>)}
  </div>;
}

/** Why a plan was turned down, asked once and optional. The answer goes to
 *  the agent as an ordinary message: it proposes another plan, and may offer
 *  to remember the reason as a preference the manager approves (D21). */
export function DismissFeedback({ disabled, onAnswer, onClose }: { disabled: boolean; onAnswer: (text: string) => void; onClose: () => void }) {
  return <div className="conversation-feedback">
    <div><span>מה לא התאים בתוכנית?</span>
      <button type="button" className="icon-button" aria-label="סגירה" onClick={onClose}><X size={14} /></button></div>
    <div className="conversation-suggestions">{DISMISS_REASONS.map((reason) => <button type="button" key={reason} disabled={disabled}
      onClick={() => onAnswer(`דחיתי את התוכנית כי ${reason}. תציע חלופה, ואם זה משהו שכדאי לזכור להבא — תציע לשמור את זה כהעדפה.`)}>{reason}</button>)}</div>
  </div>;
}

const DISMISS_REASONS = ["העובד שנבחר לא מתאים", "אני מעדיף לחלק את העומס אחרת", "חסר משהו בתוכנית", "צריך לשנות את התאריכים"];

/** What a check is called while it runs. `TOOL_LABELS` in `AgentChat` names
 *  the same checks after the fact. */
const ACTIVE_LABELS: Record<string, string> = {
  team_overview: "קורא את פרטי הצוות והכללים", read_period: "פותח את הסידור", employee_state: "בודק משמרות, שעות ואילוצים",
  coverage_gaps: "מחפש משמרות חסרות", validate_placement: "בודק שהשיבוץ תקין", find_replacements: "מחפש מי יכול להחליף",
  publish_readiness: "בודק אם אפשר לפרסם", profile_gaps: "בודק מה חסר בהגדרות", list_periods: "מחפש סידורים קודמים ועתידיים",
  workload_report: "משווה עומסים", change_history: "קורא את היסטוריית השינויים", simulate_changes: "בודק מה ישתנה בלי לשמור",
  constraints_report: "בודק אילוצים", request_inbox: "קורא את הבקשות של הצוות", preference_list: "קורא את ההעדפות השמורות",
  plan_review: "בוחן את החריגות ומתקן את ההצעה", plan_check: "מתקן את התוכנית לפי בדיקת השרת",
};
