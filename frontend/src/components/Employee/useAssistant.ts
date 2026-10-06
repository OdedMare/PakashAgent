"use client";

import { useCallback, useRef, useState } from "react";

import { askAssistant } from "@/services/api";
import type { AssistantSuggestion } from "@/types";

export interface AssistantMessage {
  role: "employee" | "assistant";
  text: string;
  suggestions?: AssistantSuggestion[];
}

// What travels back with each question. Enough for "and on Thursday?" to
// mean something; the server trims it again.
const HISTORY_SENT = 6;

/** The employee's assistant conversation (D27).
 *
 *  Held in memory only, by the page rather than the tab, so switching to
 *  "המשמרות שלי" and back keeps it. Nothing is stored server-side: these are
 *  a few questions about one's own week, and a transcript table would be
 *  something to protect for no one's benefit. */
export function useAssistant() {
  const [messages, setMessages] = useState<AssistantMessage[]>([]);
  const [asking, setAsking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inFlight = useRef(false);

  const ask = useCallback(
    async (question: string): Promise<boolean> => {
      const text = question.trim();
      if (!text || inFlight.current) return false;
      inFlight.current = true;
      setAsking(true);
      setError(null);
      const history = messages
        .slice(-HISTORY_SENT)
        .map(({ role, text: line }) => ({ role, text: line }));
      setMessages((current) => [...current, { role: "employee", text }]);
      try {
        const reply = await askAssistant({ question: text, history });
        setMessages((current) => [
          ...current,
          { role: "assistant", text: reply.answer, suggestions: reply.suggestions },
        ]);
        return true;
      } catch (reason) {
        setError(reason instanceof Error ? reason.message : "לא הצלחתי לענות כרגע");
        // The question stays on screen; dropping it would make a failure
        // look like the message was never sent.
        return false;
      } finally {
        inFlight.current = false;
        setAsking(false);
      }
    },
    [messages],
  );

  const reset = useCallback(() => {
    setMessages([]);
    setError(null);
  }, []);

  return { messages, asking, error, ask, reset };
}
