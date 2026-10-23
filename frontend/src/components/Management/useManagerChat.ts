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

// A poll reads only the running message onward: nothing before it can change
// while it runs, and re-reading every earlier plan grows with the thread.
function withTail(previous: ManagerConversation | null, tail: ManagerConversation, fromId: string) {
  if (previous?.id !== tail.id) return previous;
  const start = previous.messages.findIndex((message) => message.id === fromId);
  if (start < 0 || tail.messages[0]?.id !== fromId) return tail;
  return { ...tail, messages: [...previous.messages.slice(0, start), ...tail.messages] };
}

export function useManagerChat(workspaceId: string, scheduleId: string, visibleWeek: string, focusDate: string, onApplied: (plan?: ChatPlan) => Promise<void>) {
  const [chat, setChat] = useState<ManagerConversation | null>(null);
  const [chats, setChats] = useState<ManagerChatSummary[]>([]);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshPending, setRefreshPending] = useState<ChatPlan | null>(null);
  const inFlight = useRef(false);
  const mounted = useRef(true);
  const workingId = chat?.messages.find((message) => message.status === "working")?.id;
  const working = Boolean(workingId);

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
    if (!chatId || !workingId) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const next = await readManagerChat(chatId, workingId);
        if (cancelled) return;
        setChat((previous) => withTail(previous, next, workingId));
        setError(null);
        if (!next.messages.some((message) => message.status === "working")) {
          setChats(await listManagerChats());
          return;
        }
      } catch (reason) {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "החיבור נותק; מנסה שוב…");
      }
      if (!cancelled) timer = setTimeout(() => void poll(), 1200);
    };
    // Code-answered turns arrive finished in the send response and never
    // poll; what remains is model work, so the first look can come sooner.
    timer = setTimeout(() => void poll(), 700);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [chatId, workingId]);

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

  const syncBoard = useCallback(async (plan: ChatPlan) => {
    try {
      await onApplied(plan);
      if (mounted.current) setRefreshPending(null);
    } catch {
      if (mounted.current) setRefreshPending(plan);
      throw new Error("התוכנית נשמרה, אבל לא ניתן לטעון את הלוח המעודכן. לחצו על רענון הלוח כדי לנסות שוב.");
    }
  }, [onApplied]);

  const send = useCallback(async (content: string) => {
    if (!chatId || working || !content.trim()) return false;
    // An id survives a lost response, so re-fetching recovers the accepted turn.
    return run(async () => {
      const id = requestId();
      const latest = chat?.messages[chat.messages.length - 1];
      let next: ManagerConversation;
      try {
        next = await sendManagerMessage(chatId, { content: content.trim(), request_id: id,
          schedule_id: scheduleId || undefined, visible_week: visibleWeek, focus_date: focusDate || undefined,
          displayed_plan_id: latest?.status === "pending" ? latest.id : undefined });
      } catch (reason) {
        const recovered = await readManagerChat(chatId).catch(() => null);
        if (recovered?.messages.some((message) => message.status === "working" || message.request_id === id)) next = recovered;
        else throw reason;
      }
      if (mounted.current) setChat(next);
      if (latest?.status === "pending" && next.messages.find((message) => message.id === latest.id)?.status === "applied")
        await syncBoard(latest.payload.plan!);
      return next;
    });
  }, [chat, chatId, working, scheduleId, visibleWeek, focusDate, run, syncBoard]);

  const apply = useCallback(async (messageId: string, exceptions: boolean) => {
    if (!chatId || working) return;
    await run(async () => {
      let next: ManagerConversation | undefined;
      // Approval is idempotent by message id; recover or retry a lost response once.
      for (let attempt = 0; attempt < 2; attempt++) {
        try {
          next = await applyManagerPlan(chatId, messageId, exceptions);
          break;
        } catch (reason) {
          const recovered = await readManagerChat(chatId).catch(() => null);
          const status = recovered?.messages.find((message) => message.id === messageId)?.status;
          if (status === "applied") { next = recovered!; break; }
          if (attempt === 1 || (recovered && status !== "pending")) throw reason;
        }
      }
      const applied = next?.messages.find((message) => message.id === messageId);
      if (applied?.status !== "applied" || !applied.payload.plan)
        throw new Error("השרת לא אישר שהתוכנית נשמרה. נסו שוב להחיל את התוכנית.");
      if (mounted.current) setChat(next!);
      await syncBoard(applied.payload.plan);
      return next!;
    });
  }, [chatId, working, run, syncBoard]);

  return {
    chat, chats, busy, working, loading, error, send, apply, refreshPending,
    retryRefresh: () => chat && refreshPending ? run(async () => {
      await syncBoard(refreshPending);
      return chat;
    }) : Promise.resolve(false),
    select: (id: string) => run(() => readManagerChat(id)),
    newChat: () => run(createManagerChat),
    remove: () => chatId ? run(async () => {
      await deleteManagerChat(chatId);
      const remaining = await listManagerChats();
      return remaining.length ? readManagerChat(remaining[0].id) : createManagerChat();
    }) : Promise.resolve(false),
    // Done with this thread: drop it and start clean, rather than landing on
    // whichever older conversation `remove` would open.
    restart: () => chatId ? run(async () => {
      await deleteManagerChat(chatId);
      return createManagerChat();
    }) : Promise.resolve(false),
    dismiss: (messageId: string) => chatId ? run(() => dismissManagerPlan(chatId, messageId)) : Promise.resolve(false),
    stop: () => chatId ? run(() => stopManagerReply(chatId)) : Promise.resolve(false),
  };
}
