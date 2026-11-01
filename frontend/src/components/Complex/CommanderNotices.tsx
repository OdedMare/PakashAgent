"use client";

import { Check, Network } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { commanderNotices, managerEvents, markCommanderNoticesSeen } from "@/services/api";
import type { CommanderNotice } from "@/types";

const POLL_MS = 30_000;

/** What the מכלול commander changed in this משמרת, for its own commander
 *  (מפקד המשמרת, D43). Shown until they mark it read; a live `commander`
 *  signal re-reads it at once, and a slow poll is the backstop. Renders nothing for
 *  a משמרת outside any מכלול, or when there is nothing new. */
export function CommanderNotices({ onSeen }: { onSeen?: () => void }) {
  const [notices, setNotices] = useState<CommanderNotice[]>([]);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    commanderNotices()
      .then((answer) => setNotices(answer.notices))
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    load();
    const timer = window.setInterval(load, POLL_MS);
    let source: EventSource | null = null;
    if (typeof EventSource !== "undefined") {
      source = managerEvents();
      source.addEventListener("commander", load);
    }
    return () => {
      window.clearInterval(timer);
      source?.close();
    };
  }, [load]);

  if (notices.length === 0) return null;

  const seen = async () => {
    setBusy(true);
    try {
      await markCommanderNoticesSeen();
      setNotices([]);
      onSeen?.();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="cmd-notices" role="status" aria-live="polite">
      <Network size={16} aria-hidden="true" />
      <div>
        <strong>מפקד המכלול {notices[0].complex_name} ביצע/ה שינויים במשמרת שלך</strong>
        <ul>
          {notices.slice(0, 6).map((notice) => (
            <li key={notice.id}>
              {notice.action}
              {notice.count > 1 ? ` (${notice.count} פעמים)` : ""}
              <small> · {formatWhen(notice.created_at)}</small>
            </li>
          ))}
        </ul>
      </div>
      <button type="button" className="ghost-button" onClick={() => void seen()} disabled={busy}>
        <Check size={14} /> ראיתי
      </button>
    </div>
  );
}

function formatWhen(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString("he-IL", {
    day: "numeric", month: "numeric", hour: "2-digit", minute: "2-digit",
  });
}
