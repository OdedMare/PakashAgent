"use client";

import {
  Activity,
  AlertTriangle,
  Check,
  Eye,
  History as HistoryIcon,
  RotateCcw,
  ShieldCheck,
  Sparkles,
  X,
  Zap,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import {
  approveCopilotItem,
  dismissCopilotItem,
  getCopilotAudit,
  getCopilotInbox,
  rollbackCopilotItem,
  runCopilotNow,
  setCopilotPermission,
} from "@/services/api";
import type {
  CopilotAuditEvent,
  CopilotInboxData,
  CopilotItem,
  CopilotMode,
} from "@/types";

const ACTION_LABELS: Record<string, string> = {
  follow_up_interview: "השלמת הראיון",
  profile_review: "רענון פרופיל",
  schedule_repair: "תיקון הסידור",
  system_health: "תקינות הסוכן",
};

const ACTION_DESCRIPTIONS: Record<string, string> = {
  follow_up_interview: "זיהוי מידע שחסר כדי לתכנן סידור אמין.",
  profile_review: "בדיקה תקופתית שהצוות, המשמרות והכללים עדיין נכונים.",
  schedule_repair: "זיהוי בעיות בסידור והכנת תיקון לאישור שלך.",
};

const MODE_LABELS: Record<CopilotMode, string> = {
  observe: "צפייה",
  suggest: "הצעה",
  auto: "אוטומטי",
};

type ConsoleTab = "attention" | "permissions" | "history";

export function CopilotInbox({
  onAct,
  onOpenInterview,
  onPendingChange,
}: {
  onAct: (suggestion: string) => void;
  onOpenInterview?: () => void;
  onPendingChange?: (count: number) => void;
}) {
  const [data, setData] = useState<CopilotInboxData>();
  const [audit, setAudit] = useState<CopilotAuditEvent[]>([]);
  const [tab, setTab] = useState<ConsoleTab>("attention");
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    const [inbox, history] = await Promise.all([
      getCopilotInbox(),
      getCopilotAudit(),
    ]);
    setData(inbox);
    setAudit(history.events);
  }, []);

  useEffect(() => {
    const refresh = () => void load().catch((reason) =>
      setError(reason instanceof Error ? reason.message : "טעינת פעילות הסוכן נכשלה"),
    );
    const first = window.setTimeout(refresh, 0);
    const timer = window.setInterval(refresh, 15000);
    return () => {
      window.clearTimeout(first);
      window.clearInterval(timer);
    };
  }, [load]);

  const pending = (data?.items ?? []).filter((item) => item.status === "pending");
  const handled = (data?.items ?? []).filter((item) => item.status !== "pending");
  const proposals = pending.filter((item) => item.kind === "proposal").length;
  const observations = pending.filter((item) => item.kind === "observation").length;
  const failures = pending.filter((item) => item.kind === "failure").length;
  const health = data?.health;
  const working = Boolean(health?.running_jobs || health?.queued_jobs);

  useEffect(() => onPendingChange?.(pending.length), [onPendingChange, pending.length]);

  const act = useCallback(async (item: CopilotItem) => {
    setBusy(item.id);
    setMessage("");
    setError("");
    try {
      await approveCopilotItem(item.id);
      await load();
      if (item.action_type === "schedule_repair") {
        onAct(String(item.payload.suggestion ?? item.detail));
      } else {
        onOpenInterview?.();
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "אישור הפעולה נכשל");
    } finally {
      setBusy("");
    }
  }, [load, onAct, onOpenInterview]);

  const dismiss = useCallback(async (item: CopilotItem) => {
    setBusy(item.id);
    setError("");
    try {
      await dismissCopilotItem(item.id);
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "סגירת הפריט נכשלה");
    } finally {
      setBusy("");
    }
  }, [load]);

  const retry = useCallback(async (item: CopilotItem) => {
    setBusy(item.id);
    setMessage("");
    setError("");
    try {
      await runCopilotNow();
      await dismissCopilotItem(item.id);
      await load();
      setMessage("הבדיקה הוחזרה לתור. הסוכן יעדכן כאן את התוצאה.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "הניסיון החוזר נכשל");
    } finally {
      setBusy("");
    }
  }, [load]);

  const changePermission = useCallback(async (
    actionType: string,
    mode: CopilotMode,
  ) => {
    setBusy(actionType);
    setMessage("");
    setError("");
    try {
      await setCopilotPermission(actionType, mode);
      await load();
      setMessage(`ההרשאה עודכנה למצב ${MODE_LABELS[mode]}.`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "עדכון ההרשאה נכשל");
    } finally {
      setBusy("");
    }
  }, [load]);

  return (
    <section className="copilot-console" aria-busy={Boolean(busy)}>
      <header className="copilot-console-head">
        <div className="copilot-console-title">
          <span className="copilot-console-mark" aria-hidden="true">
            <Sparkles size={18} />
          </span>
          <div>
            <span className={`copilot-live${working ? " is-working" : ""}`}>
              <i aria-hidden="true" />
              {health?.running_jobs
                ? "בודק עכשיו"
                : health?.queued_jobs
                  ? "בדיקה ממתינה"
                  : "מוכן לבדיקה"}
            </span>
            <h2>הסוכן — פעילות יזומה</h2>
            <p>אותו סוכן שאיתו מדברים כאן עוקב אחרי הפרופיל והסידור גם כשהמסך סגור. שום שינוי בסידור לא מתבצע בלי אישור וסיבה.</p>
          </div>
        </div>
        <button
          type="button"
          className="primary-button copilot-run"
          disabled={Boolean(busy) || working}
          onClick={async () => {
            setBusy("run");
            setMessage("");
            setError("");
            try {
              await runCopilotNow();
              await load();
              setMessage("הבדיקה נוספה לתור. אפשר להמשיך לעבוד — התוצאה תופיע כאן.");
            } catch (reason) {
              setError(reason instanceof Error ? reason.message : "הפעלת הבדיקה נכשלה");
            } finally {
              setBusy("");
            }
          }}
        >
          <Zap size={15} />
          {busy === "run" ? "מוסיף לתור…" : "בדיקה עכשיו"}
        </button>
      </header>

      <div className="copilot-metrics" aria-label="מצב הפעילות היזומה של הסוכן">
        <CopilotMetric value={pending.length} label="דורש מבט" tone={failures ? "danger" : "primary"} />
        <CopilotMetric value={proposals} label="ממתין לאישור" />
        <CopilotMetric value={observations} label="לתשומת לב" />
        <CopilotMetric value={formatLastCheck(health?.last_completed_at)} label="בדיקה אחרונה" compact />
      </div>

      {error ? <p className="copilot-feedback is-error" role="alert">{error}</p> : null}
      {message ? <p className="copilot-feedback" role="status">{message}</p> : null}

      <div className="copilot-console-tabs" role="tablist" aria-label="פעילות הסוכן">
        <ConsoleTabButton active={tab === "attention"} icon={<Activity size={15} />} label="דורש מבט" count={pending.length} onClick={() => setTab("attention")} />
        <ConsoleTabButton active={tab === "permissions"} icon={<ShieldCheck size={15} />} label="עצמאות" onClick={() => setTab("permissions")} />
        <ConsoleTabButton active={tab === "history"} icon={<HistoryIcon size={15} />} label="יומן" count={audit.length} onClick={() => setTab("history")} />
      </div>

      {tab === "attention" ? (
        <div className="copilot-queue" role="tabpanel">
          {!data ? <p className="copilot-empty" aria-live="polite">טוען את פעילות הסוכן…</p> : null}
          {data && !pending.length ? (
            <div className="copilot-zero">
              <Check size={20} aria-hidden="true" />
              <strong>אין כרגע משהו שמחכה לך</strong>
              <span>הסוכן ימשיך לבדוק ברקע ויציג כאן רק פריטים חדשים.</span>
            </div>
          ) : null}
          {pending.map((item) => (
            <CopilotCard key={item.id} item={item} busy={Boolean(busy)} onApprove={() => void act(item)} onDismiss={() => void dismiss(item)} onRetry={() => void retry(item)} />
          ))}

          {handled.length ? (
            <details className="copilot-handled">
              <summary>טופל לאחרונה ({handled.length})</summary>
              <div className="copilot-handled-list">
                {handled.slice(0, 20).map((item) => (
                  <div key={item.id} className="copilot-handled-row">
                    <span>
                      <strong>{item.title}</strong>
                      <small>{statusLabel(item.status)} · {formatDate(item.updated_at ?? item.created_at)}</small>
                    </span>
                    {item.kind === "proposal" && ["approved", "applied", "dismissed"].includes(item.status) ? (
                      <button
                        type="button"
                        className="ghost-button compact"
                        aria-label={`ביטול: ${item.title}`}
                        disabled={Boolean(busy)}
                        onClick={async () => {
                          setBusy(item.id);
                          setError("");
                          try {
                            await rollbackCopilotItem(item.id);
                            await load();
                          } catch (reason) {
                            setError(reason instanceof Error ? reason.message : "ביטול הפעולה נכשל");
                          } finally {
                            setBusy("");
                          }
                        }}
                      >
                        <RotateCcw size={13} /> ביטול
                      </button>
                    ) : null}
                  </div>
                ))}
              </div>
            </details>
          ) : null}
        </div>
      ) : null}

      {tab === "permissions" ? (
        <div className="copilot-permissions" role="tabpanel">
          <div className="copilot-section-intro">
            <h3>כמה עצמאות לתת לסוכן?</h3>
            <p>ההרשאה נקבעת לכל סוג עבודה בנפרד. אפשר לשנות אותה בכל רגע.</p>
          </div>
          {(data?.permissions ?? []).map((permission) => (
            <article key={permission.action_type} className="copilot-permission-row">
              <div>
                <strong>{ACTION_LABELS[permission.action_type] ?? permission.action_type}</strong>
                <p>{ACTION_DESCRIPTIONS[permission.action_type] ?? "פעולת סוכן ברקע."}</p>
              </div>
              <div className="copilot-mode-picker" role="group" aria-label={`הרשאה עבור ${ACTION_LABELS[permission.action_type] ?? permission.action_type}`}>
                {(["observe", "suggest", "auto"] as CopilotMode[]).map((mode) => (
                  <button type="button" key={mode} className={permission.mode === mode ? "is-active" : ""} aria-pressed={permission.mode === mode} disabled={Boolean(busy)} onClick={() => void changePermission(permission.action_type, mode)}>
                    {MODE_LABELS[mode]}
                  </button>
                ))}
              </div>
            </article>
          ))}
          <p className="copilot-safety-note">
            <ShieldCheck size={15} aria-hidden="true" />
            גם במצב אוטומטי, תיקון סידור נשאר הצעה עד לאישור שלך ולכתיבת סיבה.
          </p>
        </div>
      ) : null}

      {tab === "history" ? (
        <div className="copilot-history" role="tabpanel">
          <div className="copilot-section-intro">
            <h3>יומן ביקורת</h3>
            <p>מי עשה מה, מתי, והאם המערכת הצליחה לאמת את התוצאה.</p>
          </div>
          {!audit.length ? <p className="copilot-empty">עדיין אין פעילות מתועדת.</p> : null}
          <ol className="copilot-audit">
            {audit.map((event) => (
              <li key={event.id}>
                <span className="copilot-audit-mark" aria-hidden="true" />
                <div>
                  <span className="copilot-audit-meta">
                    <strong>{eventLabel(event.event)}</strong>
                    {event.verification?.ok === true ? <em><Check size={11} /> אומת</em> : null}
                  </span>
                  {event.message ? <p>{event.message}</p> : null}
                  <small>{actorLabel(event.actor)} · {formatDate(event.created_at)}</small>
                </div>
              </li>
            ))}
          </ol>
        </div>
      ) : null}
    </section>
  );
}

function CopilotMetric({ value, label, tone = "neutral", compact = false }: { value: number | string; label: string; tone?: "neutral" | "primary" | "danger"; compact?: boolean }) {
  return (
    <div className={`copilot-metric is-${tone}${compact ? " is-compact" : ""}`}>
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}

function ConsoleTabButton({ active, icon, label, count, onClick }: { active: boolean; icon: React.ReactNode; label: string; count?: number; onClick: () => void }) {
  return (
    <button type="button" role="tab" aria-selected={active} className={active ? "is-active" : ""} onClick={onClick}>
      {icon}<span>{label}</span>{count ? <small>{count > 99 ? "99+" : count}</small> : null}
    </button>
  );
}

function CopilotCard({ item, busy, onApprove, onDismiss, onRetry }: { item: CopilotItem; busy: boolean; onApprove: () => void; onDismiss: () => void; onRetry: () => void }) {
  const warning = item.payload.warning as Record<string, unknown> | undefined;
  return (
    <article className={`copilot-item is-${item.kind}`}>
      <div className="copilot-item-topline">
        <span className="copilot-kind">
          {item.kind === "failure" ? <AlertTriangle size={13} /> : item.kind === "observation" ? <Eye size={13} /> : <Sparkles size={13} />}
          {ACTION_LABELS[item.action_type] ?? "מערכת"}
        </span>
        <time>{formatDate(item.created_at)}</time>
      </div>
      <h3>{item.title}</h3>
      <p>{item.detail}</p>
      {warning ? (
        <div className="copilot-context" aria-label="הקשר לבעיה">
          {warning.date ? <span>{String(warning.date)}</span> : null}
          {warning.shift ? <span>{String(warning.shift)}</span> : null}
          {warning.employee ? <span>{String(warning.employee)}</span> : null}
        </div>
      ) : null}
      <div className="copilot-actions">
        {item.kind === "proposal" ? (
          <button type="button" className="primary-button" disabled={busy} onClick={onApprove}>
            <Check size={14} />{item.action_type === "schedule_repair" ? "המשך להכנת תיקון" : "פתיחת ראיון המשך"}
          </button>
        ) : null}
        {item.kind === "failure" ? (
          <button type="button" className="primary-button" disabled={busy} onClick={onRetry}><RotateCcw size={14} /> ניסיון חוזר</button>
        ) : null}
        <button type="button" className="ghost-button" disabled={busy} onClick={onDismiss}><X size={14} /> {item.kind === "observation" ? "ראיתי" : "סגירה"}</button>
      </div>
    </article>
  );
}

function statusLabel(status: CopilotItem["status"]): string {
  return ({ approved: "אושר", applied: "בוצע ואומת", dismissed: "נסגר", failed: "נכשל", rolled_back: "בוטל", pending: "ממתין" })[status];
}

function eventLabel(event: string): string {
  return ({ created: "נוצר פריט חדש", approved: "הפעולה אושרה", applied: "הפעולה בוצעה", dismissed: "הפריט נסגר", rolled_back: "הפעולה בוטלה", permission_changed: "ההרשאה שונתה" })[event] ?? event;
}

function actorLabel(actor: string): string {
  return actor === "manager" ? "המנהל" : actor === "system" ? "המערכת" : actor;
}

function formatDate(value?: string | null): string {
  if (!value) return "עכשיו";
  return new Date(value).toLocaleString("he-IL", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

function formatLastCheck(value?: string | null): string {
  if (!value) return "טרם בוצעה";
  return new Date(value).toLocaleTimeString("he-IL", { hour: "2-digit", minute: "2-digit" });
}
