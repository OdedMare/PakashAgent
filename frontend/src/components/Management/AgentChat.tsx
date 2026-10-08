"use client";

import { ArrowDown, ArrowUp, CalendarDays, Check, ChevronDown, Copy, History, LoaderCircle, MessageSquare, Pencil, Plus, RotateCcw, Search, Sparkles, Square, Trash2, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Proposal } from "@/types";
import { displayDate as formatDate } from "@/components/DateInput";
import { hebrewWeekday } from "./Calendar";
import type { useManagerChat } from "./useManagerChat";
import { ChatPlanCard } from "./ChatPlanCard";
import { ChatCandidates } from "./ChatCandidates";

/** The manager's one agent: every instruction to the scheduling agent goes
 *  through this conversation. The board can open it focused on one day
 *  (`focusDate`); messages then carry that day, and the agent treats requests
 *  that name no date as being about it. */
export function AgentChat({ agent, visibleWeek, focusDate = "", focusKey, employees, draft, draftKey, boardBusy, hidden = false, onClearFocus, onPreview, onOpenReceipt, onImport }: {
  agent: ReturnType<typeof useManagerChat>; visibleWeek: string; focusDate?: string; focusKey?: number; employees: string[];
  draft?: string; draftKey?: number; boardBusy: boolean; hidden?: boolean; onClearFocus?: () => void;
  onPreview: (proposal: Proposal | null) => void; onOpenReceipt: (date: string) => void; onImport: () => void;
}) {
  const [text, setText] = useState(() => readDraft(agent.chat?.id));
  const [historyOpen, setHistoryOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [historySearch, setHistorySearch] = useState("");
  const [revising, setRevising] = useState(false);
  const input = useRef<HTMLTextAreaElement>(null);
  const log = useRef<HTMLDivElement>(null);
  const pinned = useRef(true);
  const sending = useRef(false);
  const [awayFromBottom, setAwayFromBottom] = useState(false);
  const [copied, setCopied] = useState("");
  const [copyError, setCopyError] = useState("");
  const [conversationId, setConversationId] = useState(agent.chat?.id);
  if (conversationId !== agent.chat?.id) {
    setConversationId(agent.chat?.id); setText(readDraft(agent.chat?.id)); setRevising(false); setDeleteOpen(false);
  }
  useEffect(() => {
    if (!conversationId) return;
    try {
      if (text) localStorage.setItem(`manager-chat-draft:${conversationId}`, text);
      else localStorage.removeItem(`manager-chat-draft:${conversationId}`);
    } catch { /* The composer still works when browser storage is unavailable. */ }
  }, [text, conversationId]);
  const [seeded, setSeeded] = useState(draftKey);
  if (seeded !== draftKey) { setSeeded(draftKey); if (draft) setText(draft); }
  // Opening the chat on a day puts the cursor in the composer, ready for the
  // day's instructions.
  useEffect(() => { if (focusKey && !hidden) input.current?.focus(); }, [focusKey, hidden]);
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
  useEffect(() => { pinned.current = true; }, [agent.chat?.id]);
  useEffect(() => {
    if (log.current && !hidden && pinned.current) log.current.scrollTop = log.current.scrollHeight;
  }, [messageCount, lastStatus, last?.content, last?.payload.steps?.length, agent.chat?.id, hidden]);
  useEffect(() => {
    if (input.current) {
      input.current.style.height = "auto";
      input.current.style.height = `${Math.min(200, Math.max(44, input.current.scrollHeight))}px`;
    }
  }, [text]);
  useEffect(() => { if (copied) { const timer = setTimeout(() => setCopied(""), 2000); return () => clearTimeout(timer); } }, [copied]);
  const send = async (value: string) => {
    if (disabled || sending.current || !value.trim()) return;
    sending.current = true;
    pinned.current = true;
    const draftBefore = text;
    setText(""); setRevising(false);
    try {
      if (!await agent.send(value)) setText((current) => current || draftBefore || value);
    } finally { sending.current = false; input.current?.focus(); }
  };
  const disabled = agent.busy || agent.working || agent.loading;
  const scrollBehavior = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" as const : "smooth" as const;
  return <section className="conversation" hidden={hidden} aria-label="שיחה עם סוכן הסידור">
    <header className="conversation-toolbar">
      <div className="conversation-title"><Sparkles size={17} aria-hidden="true" /><strong>{agent.chat?.title === "שיחה חדשה" ? "סוכן הסידור" : agent.chat?.title ?? "סוכן הסידור"}</strong></div>
      <div className="conversation-tools">
        <button type="button" className="icon-button" aria-label="היסטוריית שיחות" aria-expanded={historyOpen}
          onClick={() => setHistoryOpen(!historyOpen)}><History size={17} /></button>
        <button type="button" className="icon-button" aria-label="שיחה חדשה" disabled={agent.busy || agent.working || agent.loading}
          onClick={() => { void agent.newChat(); setHistoryOpen(false); }}><Plus size={19} /></button>
      </div>
    </header>
    <div className="conversation-context"><span className="conversation-context-dot" aria-hidden="true" />
      {focusDate ? <span className="conversation-focus-day"><CalendarDays size={13} aria-hidden="true" />
        {`יום ${hebrewWeekday(focusDate)} · ${formatDate(focusDate)}`}
        {onClearFocus ? <button type="button" aria-label="הסרת המיקוד ביום" title="חזרה לכל השבוע" onClick={onClearFocus}><X size={12} /></button> : null}
      </span> : visibleWeek ? `השבוע שמתחיל ב-${formatDate(visibleWeek)}` : "הצוות וכללי השיבוץ שלך"}
    </div>
    {historyOpen ? <div className="conversation-history">
      <label className="conversation-history-search"><Search size={16} aria-hidden="true" />
        <span className="sr-only">חיפוש שיחות</span><input value={historySearch} onChange={(event) => setHistorySearch(event.target.value)} placeholder="חיפוש שיחות…" />
      </label>
      <div className="conversation-history-list" aria-label="השיחות שלי">
        {agent.chats.filter((row) => row.title.includes(historySearch.trim())).map((row) => <button type="button" key={row.id}
          aria-current={row.id === agent.chat?.id ? "true" : undefined} disabled={agent.busy || agent.loading}
          onClick={async () => { if (await agent.select(row.id)) { setHistoryOpen(false); input.current?.focus(); } }}>
          <MessageSquare size={15} aria-hidden="true" /><span>{row.title}</span>
          <time dateTime={row.updated_at}>{new Date(row.updated_at).toLocaleDateString("he-IL", { timeZone: "Asia/Jerusalem", day: "numeric", month: "short" })}</time>
        </button>)}
        {!agent.chats.some((row) => row.title.includes(historySearch.trim())) ? <p>לא נמצאו שיחות.</p> : null}
      </div>
      {deleteOpen ? <div className="conversation-delete-confirm">
        <span>למחוק את השיחה? השינויים בסידור יישארו.</span>
        <button type="button" disabled={agent.busy} onClick={() => { void agent.remove(); setDeleteOpen(false); }}>מחיקת השיחה</button>
        <button type="button" onClick={() => setDeleteOpen(false)}>ביטול</button>
      </div> : <button type="button" className="ghost-button" disabled={!agent.chat || agent.busy || agent.working}
        onClick={() => setDeleteOpen(true)}><Trash2 size={14} /> מחיקת השיחה</button>}
    </div> : null}
    <div className="conversation-log" ref={log} role="log" aria-label="הודעות בשיחה" aria-relevant="additions text"
      onScroll={() => { const element = log.current; if (element) { pinned.current = element.scrollHeight - element.scrollTop - element.clientHeight < 80; setAwayFromBottom(!pinned.current); } }}>
      {agent.loading ? <p className="conversation-loading"><LoaderCircle size={17} /> טוען שיחות…</p> : null}
      {!agent.loading && !messages.length ? <div className="conversation-empty">
        <div className="conversation-empty-mark"><MessageSquare size={25} /></div>
        <h3>{focusDate ? `מה נעשה ביום ${hebrewWeekday(focusDate)}?` : "איך ננהל את הסידור היום?"}</h3>
        <p>{focusDate ? "שיבוץ, החלפה או אילוץ — נדבר על היום שנבחר בלוח." : "שיבוצים, אנשים ואילוצים. מתחילים בבקשה שלך."}</p>
        <div className="conversation-starters">{(focusDate ? DAY_STARTERS : WEEK_STARTERS).map((value) =>
          <button type="button" key={value} disabled={disabled} onClick={() => void send(value)}>{value}</button>)}</div>
      </div> : null}
      {messages.map((message) => <article id={`chat-message-${message.id}`} key={message.id} className={`conversation-message is-${message.role}${message.status === "error" ? " is-error" : ""}`}>
        <div className="conversation-speaker">{message.role === "assistant" ? <><Sparkles size={13} /> סוכן הסידור</> : "את/ה"}</div>
        {message.status === "working" ? <Thinking steps={message.payload.steps ?? []} /> :
          message.role === "assistant" ? <Markdown text={message.content} /> : <div className="conversation-text">{message.content}</div>}
        {message.payload.plan ? <ChatPlanCard message={message} employees={employees} disabled={disabled || boardBusy}
          onApply={(exceptions) => void agent.apply(message.id, exceptions)} onDismiss={() => void agent.dismiss(message.id)} onAdjust={(value) => void send(value)} /> : null}
        {message.role === "assistant" && message.status === "complete" && message.payload.results ?
          <ChatCandidates results={message.payload.results} disabled={disabled || message.id !== last?.id} onChoose={(value) => void send(value)} /> : null}
        {message.payload.question?.options.length ? <div className="conversation-options">{message.payload.question.options.map((option, index) =>
          <button type="button" key={option.label} disabled={disabled || message.id !== last?.id || message.status === "applied"}
            onClick={() => void send(option.answer)}>{index === 0 ? <Sparkles size={12} /> : null}{option.label}</button>)}</div> : null}
        {message.status !== "working" && message.payload.steps?.length ? <details className="conversation-checks"><summary><ChevronDown size={12} /> מה נבדק ({message.payload.steps.length})</summary>
          <ul>{message.payload.steps.map((step, index) => <li key={index}>{TOOL_LABELS[step.tool] ?? "בדיקת הסידור"}{step.ok ? "" : " — הבדיקה לא הושלמה"}</li>)}</ul></details> : null}
        {message.status === "error" && message.id === last?.id ? <button type="button" className="ghost-button" disabled={disabled} onClick={() => {
          const previous = [...messages].reverse().find((row) => row.role === "user"); if (previous) void send(previous.content);
        }}>ניסיון נוסף</button> : null}
        {message.payload.receipt?.starts_on ? <button type="button" className="conversation-receipt-link" onClick={() => onOpenReceipt(message.payload.receipt!.starts_on!)}><CalendarDays size={14} />פתיחת הסידור שעודכן</button> : null}
        {message.status !== "working" && message.content ? <div className="conversation-message-actions">
          <button type="button" className="icon-button" aria-label={message.role === "assistant" ? "העתקת התשובה" : "העתקת ההודעה"} title="העתקה" onClick={async () => {
            try { await navigator.clipboard.writeText(message.content); setCopied(message.id); setCopyError(""); }
            catch { setCopyError("ההעתקה לא זמינה בדפדפן הזה. אפשר לבחור ולהעתיק את הטקסט."); }
          }}>{copied === message.id ? <Check size={15} /> : <Copy size={15} />}</button>
          {message.role === "user" ? <button type="button" className="icon-button" aria-label="עריכת הבקשה כהודעת המשך" title="עריכת הבקשה כהודעת המשך" disabled={disabled}
            onClick={() => { setText(message.content); setRevising(true); input.current?.focus(); }}><Pencil size={15} /></button> : null}
          {message.id === last?.id && message.role === "assistant" && message.status === "complete" && !message.payload.plan && !message.payload.receipt ?
            <button type="button" className="icon-button" aria-label="תשובה נוספת" title="תשובה נוספת" disabled={disabled}
              onClick={() => void send("ענה מחדש על הבקשה האחרונה שלי, בניסוח אחר. זו בקשה לתשובה בלבד, ללא ביצוע או אישור שינויים.")}><RotateCcw size={15} /></button> : null}
        </div> : null}
      </article>)}
    </div>
    <div className="conversation-bottom">
    {awayFromBottom ? <button type="button" className="conversation-jump" aria-label="מעבר להודעה האחרונה"
      onClick={() => { pinned.current = true; setAwayFromBottom(false); log.current?.scrollTo({ top: log.current.scrollHeight, behavior: scrollBehavior() }); }}><ArrowDown size={17} /></button> : null}
    {preview ? <div className="conversation-pending-bar"><span><Sparkles size={14} />תוכנית ממתינה לאישור</span>
      <button type="button" onClick={() => document.getElementById(`chat-message-${last.id}`)?.scrollIntoView({ block: "nearest", behavior: scrollBehavior() })}>הצגת התוכנית</button></div> : null}
    {copyError ? <p className="conversation-error" role="status">{copyError}</p> : null}
    {agent.error ? <p className="conversation-error" role="alert">{agent.error}</p> : null}
    <form className="conversation-composer" data-tour="agent-composer" onSubmit={(event) => { event.preventDefault(); if (!disabled) void send(text); }}>
      {revising ? <div className="conversation-revising"><span>הבקשה הערוכה תישלח כהודעת המשך</span>
        <button type="button" className="icon-button" aria-label="ביטול עריכת הבקשה" onClick={() => { setRevising(false); setText(""); }}><X size={15} /></button></div> : null}
      <label className="sr-only" htmlFor="agent-composer-input">הודעה לסוכן הסידור</label>
      <textarea id="agent-composer-input" ref={input} value={text} rows={1} maxLength={4000} dir="auto" aria-describedby="agent-composer-hint" placeholder={focusDate ? `שאלו על יום ${hebrewWeekday(focusDate)} ${formatDate(focusDate)}…` : "מה תרצו לעשות בסידור?"}
        onChange={(event) => setText(event.target.value)} onKeyDown={(event) => {
          if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); if (!disabled && text.trim()) void send(text); }
        }} />
      <div className="conversation-composer-footer"><button type="button" className="icon-button" aria-label="ייבוא סידור מקובץ" title="ייבוא סידור מקובץ" onClick={onImport} disabled={boardBusy}><Plus size={19} /></button>
        <small id="agent-composer-hint">Enter לשליחה · Shift+Enter לשורה חדשה</small>
        {agent.working ? <button type="button" className="conversation-send" aria-label="עצירת הבקשה" disabled={agent.busy} onClick={() => void agent.stop()}><Square size={16} /></button> :
          <button type="submit" className="conversation-send" aria-label="שליחת הודעה" disabled={disabled || !text.trim()}>{agent.busy ? <LoaderCircle size={17} /> : <ArrowUp size={19} />}</button>}
      </div>
    </form>
    <p className="conversation-disclaimer">הסוכן יכול לטעות. בדקו את התוכנית לפני האישור.</p>
    </div>
  </section>;
}

/** What the agent is checking right now. The server saves each round's checks
 *  on the working message, and the existing poll brings them here. */
function Thinking({ steps }: { steps: { tool: string; ok: boolean }[] }) {
  const current = steps.length ? TOOL_LABELS[steps[steps.length - 1].tool] ?? "בדיקת הסידור" : "";
  return <div className="conversation-thinking" role="status"><LoaderCircle size={16} />
    <span>{current ? `${current}…` : "בודק את הסידור, האילוצים והכללים…"}
      {steps.length > 1 ? <small> · {steps.length} בדיקות עד עכשיו</small> : null}</span></div>;
}

/** Render Markdown as React elements. Raw HTML and remote images are excluded. */
export function Markdown({ text }: { text: string }) {
  return <div className="conversation-text is-rich" dir="auto"><ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml
    components={{
      img: ({ alt }) => <span>{alt}</span>,
      a: ({ children, href }) => <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>,
      table: ({ children }) => <div className="conversation-table" tabIndex={0} role="region" aria-label="טבלה בתשובה"><table>{children}</table></div>,
      pre: ({ children }) => <CodeBlock>{children}</CodeBlock>,
    }}>{text}</ReactMarkdown></div>;
}

function CodeBlock({ children }: { children: React.ReactNode }) {
  const code = useRef<HTMLPreElement>(null);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState(false);
  useEffect(() => { if (copied) { const timer = setTimeout(() => setCopied(false), 2000); return () => clearTimeout(timer); } }, [copied]);
  return <div className="conversation-code"><header><span>קוד</span><button type="button" onClick={async () => {
    try { await navigator.clipboard.writeText(code.current?.textContent ?? ""); setCopied(true); setError(false); }
    catch { setError(true); }
  }}>{copied ? <Check size={14} /> : <Copy size={14} />}{copied ? "הועתק" : "העתקת קוד"}</button></header>
    <pre ref={code} dir="ltr">{children}</pre>{error ? <small role="status">אפשר לבחור ולהעתיק את הקוד ידנית.</small> : null}</div>;
}

function readDraft(id?: string) {
  try { return id ? localStorage.getItem(`manager-chat-draft:${id}`) ?? "" : ""; }
  catch { return ""; }
}

const WEEK_STARTERS = ["תשבץ את שני כמו בשבוע שעבר", "מי יכול להחליף ברביעי?", "מי משובץ הכי הרבה בסופ״ש?", "אני רוצה להוסיף אילוץ קבוע לעובד"];
const DAY_STARTERS = ["תשבץ את היום הזה", "תמלא רק את המשמרות הפנויות ביום הזה", "איך כדאי לפתור חוסר בעובדים ביום הזה?", "מי זמין להחליף ביום הזה?"];
const TOOL_LABELS: Record<string, string> = { team_overview: "פרטי הצוות והכללים", read_period: "הסידור והסגירות", employee_state: "משמרות, שעות ואילוצים", coverage_gaps: "משמרות חסרות", validate_placement: "תקינות השיבוץ", find_replacements: "חלופות מתאימות", publish_readiness: "מוכנות לפרסום", profile_gaps: "פרטים חסרים", list_periods: "סידורים קודמים ועתידיים", workload_report: "השוואת עומסים", change_history: "היסטוריית שינויים", simulate_changes: "בדיקת ההשפעה של השינויים בלי לשמור", plan_review: "בחינת החריגות ותיקון ההצעה", plan_check: "תיקון התוכנית לפי בדיקת השרת" };
