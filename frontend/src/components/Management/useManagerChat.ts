"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { applyManagerPlan, createManagerChat, deleteManagerChat, dismissManagerPlan,
  listManagerChats, readManagerChat, sendManagerMessage, stopManagerReply } from "@/services/api";
import type { ChatPlan, ManagerChatSummary, ManagerConversation } from "@/types";

// `crypto.randomUUID` exists only in secure contexts (HTTPS/localhost), so a
// plain-HTTP LAN address needs the fallback.
function requestId() {
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
  return Array.from(crypto.getRandomValues(new Uint8Array(16)), (b) => b.toString(16).padStart(2, "0")).join("");
}

export function useManagerChat(workspaceId: string, scheduleId: string, visibleWeek: string, focusDate: string, onApplied: (plan?: ChatPlan) => Promise<void>) {
  const [chat, setChat] = useState<ManagerConversation | null>(null);
  const [chats, setChats] = useState<ManagerChatSummary[]>([]);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const inFlight = useRef(false);
  const mounted = useRef(true);
  const working = Boolean(chat?.messages.some((message) => message.status === "working"));

  useEffect(() => {
    mounted.current = true;
    let cancelled = false;
    void listManagerChats().then(async (rows) => {
      const initial = rows.length ? await readManagerChat(rows[0].id) : await createManagerChat();
      if (!cancelled) { setChats(rows); setChat(initial); }
    }).catch((reason) => {
      if (!cancelled) setError(reason instanceof Error ? reason.message : "לא ניתן לטעון שיחות");
    }).finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; mounted.current = false; };
  }, [workspaceId]);

  const chatId = chat?.id;
  useEffect(() => {
    if (!chatId || !working) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const next = await readManagerChat(chatId);
        if (cancelled) return;
        setChat(next);
        setError(null);
        if (!next.messages.some((message) => message.status === "working")) {
          setChats(await listManagerChats());
          return;
        }
      } catch (reason) {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "החיבור נותק; מנסה שוב…");
      }
      if (!cancelled) timer = setTimeout(() => void poll(), 2000);
    };
    timer = setTimeout(() => void poll(), 1200);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [chatId, working]);

  const run = useCallback(async (action: () => Promise<ManagerConversation>) => {
    if (inFlight.current) return false;
    inFlight.current = true;
    setBusy(true); setError(null);
    try {
      const next = await action();
      if (mounted.current) {
        setChat(next);
        const rows = await listManagerChats().catch(() => null);
        if (rows && mounted.current) setChats(rows);
      }
      return true;
    } catch (reason) {
      if (mounted.current) setError(reason instanceof Error ? reason.message : "לא ניתן להשלים את הפעולה");
      return false;
    } finally {
      inFlight.current = false;
      if (mounted.current) setBusy(false);
    }
  }, []);

  const send = useCallback(async (content: string) => {
    if (!chatId || working || !content.trim()) return false;
    // An id survives a lost response, so re-fetching recovers the accepted turn.
    return run(async () => {
      try {
        return await sendManagerMessage(chatId, { content: content.trim(), request_id: requestId(),
          schedule_id: scheduleId || undefined, visible_week: visibleWeek, focus_date: focusDate || undefined });
      } catch (reason) {
        const recovered = await readManagerChat(chatId).catch(() => null);
        if (recovered?.messages.some((message) => message.status === "working")) return recovered;
        throw reason;
      }
    });
  }, [chatId, working, scheduleId, visibleWeek, focusDate, run]);

  const apply = useCallback(async (messageId: string, exceptions: boolean) => {
    if (!chatId || working) return;
    await run(async () => {
      const next = await applyManagerPlan(chatId, messageId, exceptions);
      if (mounted.current) setChat(next);
      await onApplied(next.messages.find((message) => message.id === messageId)?.payload.plan);
      return next;
    });
  }, [chatId, working, run, onApplied]);

  return {
    chat, chats, busy, working, loading, error, send, apply,
    select: (id: string) => run(() => readManagerChat(id)),
    newChat: () => run(createManagerChat),
    remove: () => chatId ? run(async () => {
      await deleteManagerChat(chatId);
      const remaining = await listManagerChats();
      return remaining.length ? readManagerChat(remaining[0].id) : createManagerChat();
    }) : Promise.resolve(false),
    dismiss: (messageId: string) => chatId ? run(() => dismissManagerPlan(chatId, messageId)) : Promise.resolve(false),
    stop: () => chatId ? run(() => stopManagerReply(chatId)) : Promise.resolve(false),
  };
}
