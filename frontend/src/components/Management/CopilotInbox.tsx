"use client";

import {
  Check,
  Clock3,
  History as HistoryIcon,
  RotateCcw,
  ShieldCheck,
  Sparkles,
  X,
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
};

export function CopilotInbox({
  onAct,
  onOpenInterview,
}: {
  onAct: (suggestion: string) => void;
  onOpenInterview?: () => void;
}) {
  const [data, setData] = useState<CopilotInboxData>();
  const [audit, setAudit] = useState<CopilotAuditEvent[]>([]);
  const [showAudit, setShowAudit] = useState(false);
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState("");

  const load = useCallback(async () => {
    const [inbox, history] = await Promise.all([
      getCopilotInbox(),
      getCopilotAudit(),
    ]);
    setData(inbox);
    setAudit(history.events);
  }, []);

  useEffect(() => {
    const first = window.setTimeout(
      () => void load().catch((reason) =>
        setMessage(reason instanceof Error ? reason.message : "טעינת הקופיילוט נכשלה"),
      ),
      0,
    );
    const timer = window.setInterval(() => void load().catch(() => undefined), 15000);
    return () => {
      window.clearTimeout(first);
      window.clearInterval(timer);
    };
  }, [load]);

  const act = useCallback(
    async (item: CopilotItem) => {
      setBusy(item.id);
      setMessage("");
      try {
        await approveCopilotItem(item.id);
        if (item.action_type === "schedule_repair") {
          onAct(String(item.payload.suggestion ?? item.detail));
        } else {
          onOpenInterview?.();
        }
        await load();
      } catch (reason) {
        setMessage(reason instanceof Error ? reason.message : "אישור הפעולה נכשל");
      } finally {
        setBusy("");
      }
    },
    [load, onAct, onOpenInterview],
  );

  const pending = (data?.items ?? []).filter((item) => item.status === "pending");
  const handled = (data?.items ?? []).filter((item) => item.status !== "pending");

  return (
    <section className="copilot-inbox" aria-busy={Boolean(busy)}>
      <header className="copilot-header">
        <div>
          <h3><Sparkles size={15} /> קופיילוט</h3>
          <p>עובד גם כשהמסך סגור. כל פעולה נשמרת וניתנת לבדיקה.</p>
        </div>
        <button
          type="button"
          className="ghost-button"
          disabled={Boolean(busy)}
          onClick={async () => {
            setBusy("run");
            try {
              await runCopilotNow();
              setMessage("הבדיקה נוספה לתור ותופיע כאן כשהיא תסתיים.");
            } catch (reason) {
              setMessage(reason instanceof Error ? reason.message : "הפעלת הבדיקה נכשלה");
            } finally {
              setBusy("");
            }
          }}
        >
          <Clock3 size={14} /> בדיקה עכשיו
        </button>
      </header>

      {message ? <p className="copilot-message">{message}</p> : null}

      <div className="copilot-permissions">
        <h4><ShieldCheck size={14} /> הרשאות לפי פעולה</h4>
        {(data?.permissions ?? []).map((permission) => (
          <label key={permission.action_type}>
            <span>{ACTION_LABELS[permission.action_type] ?? permission.action_type}</span>
            <select
              value={permission.mode}
              disabled={Boolean(busy)}
              onChange={async (event) => {
                const mode = event.target.value as CopilotMode;
                setBusy(permission.action_type);
                try {
                  await setCopilotPermission(permission.action_type, mode);
                  await load();
                } finally {
                  setBusy("");
                }
              }}
            >
              <option value="observe">רק לצפות</option>
              <option value="suggest">להציע ולאשר</option>
              <option value="auto">אוטומטי</option>
            </select>
          </label>
        ))}
        <small>תיקון סידור תמיד נשאר לאישור, גם במצב אוטומטי.</small>
      </div>

      <div className="copilot-items">
        <h4>ממתין לטיפול {pending.length ? `(${pending.length})` : ""}</h4>
        {!data ? <p className="copilot-empty">טוען…</p> : null}
        {data && !pending.length ? <p className="copilot-empty">אין כרגע פעולה שמחכה לך.</p> : null}
        {pending.map((item) => (
          <article key={item.id} className={`copilot-item is-${item.kind}`}>
            <span className="copilot-kind">{ACTION_LABELS[item.action_type] ?? "מערכת"}</span>
            <strong>{item.title}</strong>
            <p>{item.detail}</p>
            <div className="copilot-actions">
              {item.kind === "proposal" ? (
                <button type="button" className="primary-button" disabled={Boolean(busy)} onClick={() => void act(item)}>
                  <Check size={14} />
                  {item.action_type === "schedule_repair" ? "הכנת תיקון" : "פתיחת ראיון המשך"}
                </button>
              ) : null}
              <button
                type="button"
                className="ghost-button"
                disabled={Boolean(busy)}
                onClick={async () => {
                  setBusy(item.id);
                  try { await dismissCopilotItem(item.id); await load(); }
                  finally { setBusy(""); }
                }}
              >
                <X size={14} /> סגירה
              </button>
            </div>
          </article>
        ))}
      </div>

      {handled.length ? (
        <details className="copilot-handled">
          <summary>פעולות שטופלו ({handled.length})</summary>
          {handled.slice(0, 20).map((item) => (
            <div key={item.id} className="copilot-handled-row">
              <span>{item.title}</span>
              <small>{statusLabel(item.status)}</small>
              {["approved", "applied", "dismissed"].includes(item.status) ? (
                <button type="button" className="icon-button subtle" title="ביטול הפעולה" onClick={async () => {
                  setBusy(item.id);
                  try { await rollbackCopilotItem(item.id); await load(); }
                  catch (reason) { setMessage(reason instanceof Error ? reason.message : "הביטול נכשל"); }
                  finally { setBusy(""); }
                }}><RotateCcw size={13} /></button>
              ) : null}
            </div>
          ))}
        </details>
      ) : null}

      <button type="button" className="copilot-audit-toggle" onClick={() => setShowAudit((value) => !value)}>
        <HistoryIcon size={14} /> יומן ביקורת ({audit.length})
      </button>
      {showAudit ? (
        <ol className="copilot-audit">
          {audit.map((event) => (
            <li key={event.id}>
              <strong>{eventLabel(event.event)}</strong>
              <span>{event.message}</span>
              {event.created_at ? <time>{new Date(event.created_at).toLocaleString("he-IL")}</time> : null}
            </li>
          ))}
        </ol>
      ) : null}
    </section>
  );
}

function statusLabel(status: CopilotItem["status"]): string {
  return ({
    approved: "אושר",
    applied: "בוצע ואומת",
    dismissed: "נסגר",
    failed: "נכשל",
    rolled_back: "בוטל",
    pending: "ממתין",
  })[status];
}

function eventLabel(event: string): string {
  return ({
    created: "נוצר",
    approved: "אושר",
    applied: "בוצע",
    dismissed: "נסגר",
    rolled_back: "בוטל",
    permission_changed: "הרשאה שונתה",
  })[event] ?? event;
}
