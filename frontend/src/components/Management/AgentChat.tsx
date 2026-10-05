"use client";

import { Check, CheckCircle2, ChevronDown, History, LoaderCircle, MessageSquare, Plus, Send, Sparkles, Square, Trash2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { ChatPlan, ManagerChatMessage, Proposal } from "@/types";
import { displayDate as formatDate } from "@/components/DateInput";
import { useManagerChat } from "./useManagerChat";

export function AgentChat({ workspaceId, scheduleId, visibleWeek, employees, draft, draftKey, boardBusy, onApplied, onPreview }: {
  workspaceId: string; scheduleId: string; visibleWeek: string; employees: string[];
  draft?: string; draftKey?: number; boardBusy: boolean;
  onApplied: () => Promise<void>; onPreview: (proposal: Proposal | null) => void;
}) {
  const agent = useManagerChat(workspaceId, scheduleId, visibleWeek, onApplied);
  const [text, setText] = useState("");
  const [historyOpen, setHistoryOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const input = useRef<HTMLTextAreaElement>(null);
  const log = useRef<HTMLDivElement>(null);
  const [seeded, setSeeded] = useState(draftKey);
  if (seeded !== draftKey) { setSeeded(draftKey); if (draft) setText(draft); }
  const messages = agent.chat?.messages ?? [];
  const last = messages[messages.length - 1];
  const preview = last?.status === "pending" ? last.payload.plan : undefined;
  useEffect(() => {
    onPreview(preview?.kind === "changes" ? {
      schedule_id: preview.schedule_id, reply: last?.content ?? "", needs_reason: false, needs_input: false,
      pending_request: "", agent_reason: preview.agent_reason, stated_reason: preview.reason,
      operations: preview.operations, constraints: preview.constraints, profile_operations: [],
      warnings: preview.warnings as Proposal["warnings"],
    } : null);
  }, [preview, last?.content, onPreview]);
  const messageCount = messages.length;
  const lastStatus = last?.status;
  useEffect(() => { if (log.current) log.current.scrollTop = log.current.scrollHeight; }, [messageCount, lastStatus, agent.chat?.id]);
  const send = async (value: string) => {
    if (await agent.send(value)) { setText(""); input.current?.focus(); }
  };
  const disabled = agent.busy || agent.working || agent.loading;
  return <section className="conversation" aria-label="שיחה עם סוכן הסידור">
    <header className="conversation-toolbar">
      <div className="conversation-title"><Sparkles size={17} aria-hidden="true" /><strong>סוכן הסידור</strong></div>
      <div className="conversation-tools">
        <button type="button" className="icon-button" aria-label="היסטוריית שיחות" aria-expanded={historyOpen}
          onClick={() => setHistoryOpen(!historyOpen)}><History size={17} /></button>
        <button type="button" className="icon-button" aria-label="שיחה חדשה" disabled={agent.busy || agent.loading}
          onClick={() => { void agent.newChat(); setText(""); setHistoryOpen(false); }}><Plus size={19} /></button>
      </div>
    </header>
    <div className="conversation-context"><span className="conversation-context-dot" aria-hidden="true" />
      {visibleWeek ? `השבוע שמתחיל ב-${formatDate(visibleWeek)}` : "הצוות וכללי השיבוץ שלך"}
      <span>המלצות מתבצעות רק באישור שלך</span>
    </div>
    {historyOpen ? <div className="conversation-history">
      <label htmlFor="manager-conversation-picker">השיחות שלי</label>
      <select id="manager-conversation-picker" value={agent.chat?.id ?? ""} disabled={agent.busy}
        onChange={(event) => { void agent.select(event.target.value); setText(""); setDeleteOpen(false); }}>
        {!agent.chats.some((row) => row.id === agent.chat?.id) && agent.chat ? <option value={agent.chat.id}>{agent.chat.title}</option> : null}
        {agent.chats.map((row) => <option value={row.id} key={row.id}>{row.title}</option>)}
      </select>
      {deleteOpen ? <div className="conversation-delete-confirm">
        <span>למחוק את השיחה? השינויים בסידור יישארו.</span>
        <button type="button" disabled={agent.busy} onClick={() => { void agent.remove(); setDeleteOpen(false); }}>מחיקת השיחה</button>
        <button type="button" onClick={() => setDeleteOpen(false)}>ביטול</button>
      </div> : <button type="button" className="ghost-button" disabled={!agent.chat || agent.busy || agent.working}
        onClick={() => setDeleteOpen(true)}><Trash2 size={14} /> מחיקת השיחה</button>}
    </div> : null}
    <div className="conversation-log" ref={log} role="log" aria-label="הודעות בשיחה" aria-relevant="additions text">
      {agent.loading ? <p className="conversation-loading"><LoaderCircle size={17} /> טוען שיחות…</p> : null}
      {!agent.loading && !messages.length ? <div className="conversation-empty">
        <div className="conversation-empty-mark"><MessageSquare size={25} /></div>
        <h3>מה צריך לפתור בסידור?</h3><p>אפשר לבנות שבוע, למצוא מחליפים, להשוות עומסים או לעדכן את הצוות והכללים.</p>
        <div className="conversation-starters">{["תשבץ את השבוע הקרוב", "מי עובד הכי הרבה השבוע?", "מי יכול למלא את המשמרות הפנויות?", "תוסיף עובד חדש"].map((value) =>
          <button type="button" key={value} disabled={disabled} onClick={() => void send(value)}>{value}</button>)}</div>
      </div> : null}
      {messages.map((message) => <article key={message.id} className={`conversation-message is-${message.role}${message.status === "error" ? " is-error" : ""}`}>
        <div className="conversation-speaker">{message.role === "assistant" ? <><Sparkles size={13} /> סוכן הסידור</> : "את/ה"}</div>
        {message.status === "working" ? <div className="conversation-thinking" role="status"><LoaderCircle size={16} /> בודק את הסידור, האילוצים והכללים…</div> : <div className="conversation-text">{message.content}</div>}
        {message.payload.plan ? <PlanCard message={message} employees={employees} disabled={disabled || boardBusy}
          onApply={(exceptions) => void agent.apply(message.id, exceptions)} onDismiss={() => void agent.dismiss(message.id)} onAdjust={(value) => void send(value)} /> : null}
        {message.payload.question?.options.length ? <div className="conversation-options">{message.payload.question.options.map((option, index) =>
          <button type="button" key={option.label} disabled={disabled || message.id !== last?.id || message.status === "applied"}
            onClick={() => void send(option.answer)}>{index === 0 ? <Sparkles size={12} /> : null}{option.label}</button>)}</div> : null}
        {message.payload.steps?.length ? <details className="conversation-checks"><summary><ChevronDown size={12} /> מה נבדק ({message.payload.steps.length})</summary>
          <ul>{message.payload.steps.map((step, index) => <li key={index}>{TOOL_LABELS[step.tool] ?? "בדיקת הסידור"}{step.ok ? "" : " — הבדיקה לא הושלמה"}</li>)}</ul></details> : null}
        {message.status === "error" && message.id === last?.id ? <button type="button" className="ghost-button" disabled={disabled} onClick={() => {
          const previous = [...messages].reverse().find((row) => row.role === "user"); if (previous) void send(previous.content);
        }}>ניסיון נוסף</button> : null}
      </article>)}
    </div>
    {agent.error ? <p className="conversation-error" role="alert">{agent.error}</p> : null}
    <form className="conversation-composer" onSubmit={(event) => { event.preventDefault(); if (!disabled) void send(text); }}>
      <label className="sr-only" htmlFor="agent-composer-input">הודעה לסוכן הסידור</label>
      <textarea id="agent-composer-input" ref={input} value={text} rows={2} maxLength={4000} placeholder="בקשו שינוי, שאלו שאלה או המשיכו את השיחה…"
        onChange={(event) => setText(event.target.value)} onKeyDown={(event) => {
          if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); if (!disabled && text.trim()) void send(text); }
        }} />
      <div className="conversation-composer-footer"><small>Enter לשליחה · Shift+Enter לשורה חדשה</small>
        {agent.working ? <button type="button" className="conversation-send" aria-label="עצירת הבקשה" disabled={agent.busy} onClick={() => void agent.stop()}><Square size={16} /></button> :
          <button type="submit" className="conversation-send" aria-label="שליחת הודעה" disabled={disabled || !text.trim()}>{agent.busy ? <LoaderCircle size={17} /> : <Send size={17} />}</button>}
      </div>
    </form>
  </section>;
}

function PlanCard({ message, employees, disabled, onApply, onDismiss, onAdjust }: {
  message: ManagerChatMessage; employees: string[]; disabled: boolean; onApply: (exceptions: boolean) => void;
  onDismiss: () => void; onAdjust: (text: string) => void;
}) {
  const plan = message.payload.plan!;
  const [accepted, setAccepted] = useState(false);
  const pending = message.status === "pending";
  const conflicts = [...new Set([...plan.warnings.map((warning) => warning.message), ...plan.exceptions])];
  const assignments = plan.generated?.assignments ?? plan.operations;
  return <div className={`conversation-plan${message.status === "applied" ? " is-applied" : ""}`}>
    <header><span>{message.status === "applied" ? <CheckCircle2 size={15} /> : <Sparkles size={15} />}
      {message.status === "applied" ? "הוחל בסידור" : PLAN_LABELS[plan.kind]}</span><small>{pending ? "ממתין לאישור שלך" : STATUS_LABELS[message.status] ?? ""}</small></header>
    {plan.agent_reason ? <p className="conversation-plan-reason">{plan.agent_reason}</p> : null}
    {plan.generated ? <p>{formatDate(plan.starts_on!)} – {formatDate(plan.ends_on!)} · {assignments.length} שיבוצים</p> : null}
    {assignments.length ? <details className="conversation-plan-rows" open={assignments.length <= 14}><summary>השיבוצים בתוכנית ({assignments.length})</summary>
      <ul>{assignments.map((operation, index) => <li key={index}>
        <span className="conversation-operation-action">{"action" in operation ? ACTION_LABELS[String(operation.action)] : "שיבוץ"}</span>
        <div><strong>{operation.employee}</strong><span>{operation.shift} · {formatDate(operation.date)}</span>
          {"with_employee" in operation && typeof operation.with_employee === "string" && operation.with_employee ? <span>עם {operation.with_employee}</span> : null}
          {pending && (!("action" in operation) || operation.action === "assign") ? <label className="conversation-replacement"><span>בחירת עובד אחר</span>
            <select disabled={disabled} value={operation.employee} onChange={(event) => onAdjust(
              `בתוכנית האחרונה, במשמרת ${operation.shift} בתאריך ${operation.date}, הצע את ${event.target.value} במקום ${operation.employee}. שמור את כל שאר השינויים והאילוצים בתוכנית והצג תוכנית מלאה מעודכנת לאישור.`,
            )}>{employees.map((name) => <option key={name} value={name}>{name}</option>)}</select>
          </label> : null}
        </div>
      </li>)}</ul>
    </details> : null}
    {plan.constraints.length ? <div className="conversation-plan-constraints"><strong>עדכון זמינות</strong>
      {plan.constraints.map((row, index) => <p key={index}>{row.employee} · {formatDate(row.date)}{row.shift ? ` · ${row.shift}` : " · כל היום"} · {row.available ? "זמין/ה" : "לא זמין/ה"}</p>)}</div> : null}
    {plan.kind === "profile" ? <ProfileChanges plan={plan} /> : null}
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
const PLAN_LABELS: Record<ChatPlan["kind"], string> = { changes: "תוכנית שינויים", profile: "עדכון פרטי הצוות", generate: "סידור מוצע", publish: "פרסום הסידור", unpublish: "החזרה לטיוטה", clear: "פינוי השיבוצים" };
const STATUS_LABELS: Record<string, string> = { applied: "בוצע", superseded: "הוחלף בהצעה חדשה", dismissed: "בוטל" };
const VALUE_LABELS: Record<string, string> = { round: "סבב", triplet: "תלתון", hamshushim: "חמשושים", shushim: "שושים", standard: "סדיר", reserve: "מילואים", overlap: "חפיפה", hard: "כלל חובה", soft: "העדפה" };
const FIELD_LABELS: Record<string, string> = { employees: "אנשי צוות", shifts: "סוגי משמרות", rules: "כללי שיבוץ", workplace: "פרטי היחידה", name: "שם", role: "תפקיד", eligible_shifts: "משמרות מתאימות", rotation_group: "קבוצת יציאות", exit_pattern: "מבנה יציאות", service_type: "סוג שירות", start_time: "התחלה", end_time: "סיום", headcount: "מספר עובדים", notes: "הערות", text: "כלל", priority: "עדיפות", staffing: "תקינה", required_roles: "תפקידים נדרשים", is_shift_manager: "אחראי משמרת", can_train: "יכול להדריך", counts_toward_staffing: "נספר בתקינה", is_on_call: "כוננות", days: "ימים", hour_weight: "משקל שעות", recurring_constraints: "אילוצים קבועים", audit_policy: "מדיניות בקרה", max_weekly_hours: "מקסימום שעות בשבוע", min_rest_hours: "מינימום שעות מנוחה", max_consecutive_days: "מקסימום ימים רצופים", rest_policy: "מדיניות מנוחה", fairness_policy: "איזון עומסים", weekend_policy: "מדיניות סופי שבוע", conflict_policy: "טיפול בהתנגשויות", training_policy: "מדיניות הכשרה", rotation_mode: "מבנה היחידה", first_closure_date: "עוגן הסבב", first_closure_group: "קבוצת העוגן", summary: "סיכום", dependencies: "תלויות", availability_process: "תהליך זמינות", constraint_deadline: "מועד הגשת אילוצים" };
const TOOL_LABELS: Record<string, string> = { team_overview: "פרטי הצוות והכללים", read_period: "הסידור והסגירות", employee_state: "משמרות, שעות ואילוצים", coverage_gaps: "משמרות חסרות", validate_placement: "תקינות השיבוץ", find_replacements: "חלופות מתאימות", publish_readiness: "מוכנות לפרסום", profile_gaps: "פרטים חסרים", list_periods: "סידורים קודמים ועתידיים", workload_report: "השוואת עומסים", change_history: "היסטוריית שינויים" };
