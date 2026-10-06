"use client";

import { Check, CheckCircle2, Sparkles } from "lucide-react";
import { useState } from "react";
import type { ChatPlan, ManagerChatMessage } from "@/types";
import { displayDate as formatDate } from "@/components/DateInput";

export function ChatPlanCard({ message, employees, disabled, onApply, onDismiss, onAdjust }: {
  message: ManagerChatMessage; employees: string[]; disabled: boolean; onApply: (exceptions: boolean) => void;
  onDismiss: () => void; onAdjust: (text: string) => void;
}) {
  const plan = message.payload.plan!;
  const [accepted, setAccepted] = useState(false);
  const pending = message.status === "pending";
  const conflicts = [...new Set([...plan.warnings.filter((warning) => !["unfilled", "missing_role", "missing_commander"].includes(warning.code ?? "") && warning.severity !== "notice").map((warning) => warning.message), ...plan.exceptions])];
  const assignments = plan.generated?.assignments ?? plan.operations;
  return <div className={`conversation-plan${message.status === "applied" ? " is-applied" : ""}`}>
    <header><span>{message.status === "applied" ? <CheckCircle2 size={15} /> : <Sparkles size={15} />}
      {message.status === "applied" ? "הוחל בסידור" : PLAN_LABELS[plan.kind]}</span><small>{pending ? "ממתין לאישור שלך" : STATUS_LABELS[message.status] ?? ""}</small></header>
    {plan.agent_reason ? <p className="conversation-plan-reason">{plan.agent_reason}</p> : null}
    {plan.generated ? <p>{formatDate(plan.starts_on!)} – {formatDate(plan.ends_on!)} · {assignments.length} שיבוצים</p> : null}
    {plan.kind === "retire" ? <p>סיום העבודה של <strong>{plan.employee}</strong> החל מ־{formatDate(plan.effective_date!)}. המשמרות המפורטות יפונו; ההיסטוריה תישמר.</p> : null}
    {plan.coverage ? <section className="conversation-coverage" aria-label="כיסוי המשמרות בתוכנית">
      <header><strong>{plan.coverage.complete ? "כל המשמרות מאוישות" : "תוכנית חלקית — נשארו חוסרים"}</strong>
        <span>{plan.coverage.slots.filter((row) => row.complete).length}/{plan.coverage.slots.length} משמרות מלאות</span></header>
      <div>{plan.coverage.slots.map((slot) => <div className={slot.complete ? "is-covered" : "is-gap"} key={`${slot.date}:${slot.shift}`}>
        <span><strong>{slot.shift}</strong><small>{formatDate(slot.date)} · <bdi>{slot.start_time}–{slot.end_time}</bdi></small></span>
        <span>{slot.assigned}/{slot.required ?? "?"}<small>{slot.complete ? "מאוישת" : "דורשת טיפול"}</small></span>
        {slot.problems.length ? <p>{slot.problems.join(" · ")}</p> : null}
      </div>)}</div>
    </section> : null}
    {assignments.length ? <details className="conversation-plan-rows" open={assignments.length <= 14}><summary>השיבוצים בתוכנית ({assignments.length})</summary>
      <ul>{assignments.map((operation, index) => <li key={index}>
        <span className="conversation-operation-action">{"action" in operation ? ACTION_LABELS[String(operation.action)] : "שיבוץ"}</span>
        <div><strong>{operation.employee}</strong><span>{operation.shift} · {formatDate(operation.date)}</span>
          {"with_employee" in operation && typeof operation.with_employee === "string" && operation.with_employee ? <span>עם {operation.with_employee}</span> : null}
          {pending && (!("action" in operation) || operation.action === "assign") && !plan.preserved_assignments?.some((row) =>
            row.employee === operation.employee && row.shift === operation.shift && row.date === operation.date) ? <label className="conversation-replacement"><span>בחירת עובד אחר</span>
            <select disabled={disabled} value={operation.employee} onChange={(event) => onAdjust(
              `בתוכנית האחרונה, במשמרת ${operation.shift} בתאריך ${operation.date}, הצע את ${event.target.value} במקום ${operation.employee}. שמור את כל שאר השינויים והאילוצים בתוכנית והצג תוכנית מלאה מעודכנת לאישור.${plan.generated ? " זהו תיקון לתצוגה המקדימה של השבוע שנוצר; בנה תצוגה מעודכנת לאותם תאריכים עם כל שאר הבחירות בתוכנית." : ""}`,
            )}>{employees.map((name) => <option key={name} value={name}>{name}</option>)}</select>
          </label> : null}
        </div>
      </li>)}</ul>
    </details> : null}
    {plan.constraints.length ? <div className="conversation-plan-constraints"><strong>עדכון זמינות</strong>
      {plan.constraints.map((row, index) => <p key={index}>{row.employee} · {formatDate(row.date)}{row.shift ? ` · ${row.shift}` : " · כל היום"} · {row.available ? "זמין/ה" : "לא זמין/ה"}</p>)}</div> : null}
    {plan.profile_after ? <ProfileChanges plan={plan} /> : null}
    {conflicts.length ? <div className="conversation-plan-conflicts"><strong>חריגות שדורשות אישור</strong><ul>{conflicts.map((conflict) => <li key={conflict}>{conflict}</li>)}</ul>
      {pending ? <label><input type="checkbox" checked={accepted} onChange={(event) => setAccepted(event.target.checked)} disabled={disabled} />אני מאשר/ת את החריגות לשינוי הזה. הכללים השמורים לא ישתנו.</label> : null}
    </div> : null}
    {pending ? <div className="conversation-plan-actions"><button type="button" className="primary-button" disabled={disabled || (conflicts.length > 0 && !accepted)}
      onClick={() => onApply(accepted)}><Check size={15} />{plan.kind === "profile" ? "אישור העדכון" : "החלת התוכנית"}</button>
      <button type="button" className="ghost-button" disabled={disabled} onClick={onDismiss}>ביטול</button></div> : null}
    {message.status === "applied" ? <p className="conversation-plan-receipt">{message.payload.receipt?.message ?? "השינוי בוצע"}</p> : null}
  </div>;
}

function ProfileChanges({ plan }: { plan: ChatPlan }) {
  return <div className="conversation-profile-diff">{Object.keys(plan.profile_after ?? {}).map((key) => {
    const before = plan.profile_before?.[key], after = plan.profile_after?.[key];
    if (Array.isArray(after)) {
      const old = Array.isArray(before) ? before : [];
      const changed = after.filter((row) => !old.some((item) => JSON.stringify(item) === JSON.stringify(row)));
      const removed = old.filter((row) => !after.some((item) => JSON.stringify(item) === JSON.stringify(row)));
      return <div key={key}><strong>{FIELD_LABELS[key] ?? "עדכון מדיניות"}</strong>
        {removed.length ? <p><span className="conversation-diff-label">לפני</span>{describe(removed)}</p> : null}
        {changed.length ? <p><span className="conversation-diff-label">אחרי</span>{describe(changed)}</p> : null}</div>;
    }
    return <div key={key}><strong>{FIELD_LABELS[key] ?? "עדכון מדיניות"}</strong>
      <p><span className="conversation-diff-label">לפני</span>{describe(before) || "לא הוגדר"}</p>
      <p><span className="conversation-diff-label">אחרי</span>{describe(after)}</p></div>;
  })}</div>;
}

function describe(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "boolean") return value ? "כן" : "לא";
  if (Array.isArray(value)) return value.map(describe).filter(Boolean).join(" · ");
  if (typeof value === "object") return Object.entries(value).map(([key, item]) => {
    const rendered = describe(item); return rendered ? `${FIELD_LABELS[key] ? FIELD_LABELS[key] + ": " : ""}${rendered}` : "";
  }).filter(Boolean).join(" · ");
  return VALUE_LABELS[String(value)] ?? String(value);
}
const ACTION_LABELS: Record<string, string> = { assign: "שיבוץ", remove: "הסרה", swap: "החלפה" };
const PLAN_LABELS: Record<ChatPlan["kind"], string> = { changes: "תוכנית שינויים", profile: "עדכון פרטי הצוות", generate: "סידור מוצע", publish: "פרסום הסידור", unpublish: "החזרה לטיוטה", clear: "פינוי השיבוצים", retire: "סיום עבודה", restructure: "מבנה משמרות ושיבוץ מעודכן" };
const STATUS_LABELS: Record<string, string> = { applied: "בוצע", superseded: "הוחלף בהצעה חדשה", dismissed: "בוטל" };
const VALUE_LABELS: Record<string, string> = { round: "סבב", triplet: "תלתון", hamshushim: "חמשושים", shushim: "שושים", standard: "סדיר", reserve: "מילואים", overlap: "חפיפה", hard: "כלל חובה", soft: "העדפה" };
const FIELD_LABELS: Record<string, string> = { employees: "אנשי צוות", shifts: "סוגי משמרות", rules: "כללי שיבוץ", workplace: "פרטי היחידה", name: "שם", role: "תפקיד", eligible_shifts: "משמרות מתאימות", rotation_group: "קבוצת יציאות", exit_pattern: "מבנה יציאות", service_type: "סוג שירות", start_time: "התחלה", end_time: "סיום", headcount: "מספר עובדים", notes: "הערות", text: "כלל", priority: "עדיפות", staffing: "תקינה", required_roles: "תפקידים נדרשים", is_shift_manager: "אחראי משמרת", can_train: "יכול להדריך", counts_toward_staffing: "נספר בתקינה", is_on_call: "כוננות", days: "ימים", hour_weight: "משקל שעות", recurring_constraints: "אילוצים קבועים", audit_policy: "מדיניות בקרה", max_weekly_hours: "מקסימום שעות בשבוע", min_rest_hours: "מינימום שעות מנוחה", max_consecutive_days: "מקסימום ימים רצופים", rest_policy: "מדיניות מנוחה", fairness_policy: "איזון עומסים", weekend_policy: "מדיניות סופי שבוע", conflict_policy: "טיפול בהתנגשויות", training_policy: "מדיניות הכשרה", rotation_mode: "מבנה היחידה", first_closure_date: "עוגן הסבב", first_closure_group: "קבוצת העוגן", summary: "סיכום", dependencies: "תלויות", availability_process: "תהליך זמינות", constraint_deadline: "מועד הגשת אילוצים" };
