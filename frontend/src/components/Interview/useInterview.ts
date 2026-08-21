"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  answerInterview,
  endInterview,
  retryInterview,
  resumeInterview,
  startInterview,
} from "@/services/api";
import type { InterviewTurn } from "@/types";

/** The interview lives server-side; this holds only the session id, so a
 *  refresh resumes the same conversation rather than starting a second one.
 *  Resuming replays the stored question and costs no model call. */
const STORAGE_KEY = "pakash.interview.session";
const POLL_INTERVAL_MS = 1_000;

function wait(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

export interface InterviewState {
  turn: InterviewTurn | null;
  busy: boolean;
  error: string | null;
  start: () => void;
  answer: (content: string) => void;
  /** Close the interview with what has been collected so far. Resolves once
   *  the profile is stored, so the caller can leave for the management area
   *  knowing there is something there to render. */
  end: () => Promise<void>;
  reset: () => void;
  retry: () => void;
}

export function useInterview(): InterviewState {
  const [turn, setTurn] = useState<InterviewTurn | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const operation = useRef(0);
  // The request to issue when the boss presses retry. After a background
  // failure this becomes `/retry`, never the original answer POST: that
  // answer is already stored and sending it twice would corrupt the thread.
  const lastAction = useRef<(() => Promise<InterviewTurn>) | null>(null);

  const run = useCallback(async (action: () => Promise<InterviewTurn>) => {
    const currentOperation = ++operation.current;
    setBusy(true);
    setError(null);
    try {
      let next = await action();
      if (operation.current !== currentOperation) return;
      window.localStorage.setItem(STORAGE_KEY, next.session_id);
      setTurn(next);
      while (next.status === "processing") {
        await wait(POLL_INTERVAL_MS);
        if (operation.current !== currentOperation) return;
        next = await resumeInterview(next.session_id);
        setTurn(next);
      }
      if (next.status === "error") {
        lastAction.current = () => retryInterview(next.session_id);
        throw new Error(next.error || "יצירת השאלה נכשלה. אפשר לנסות שוב.");
      }
    } catch (reason) {
      if (operation.current !== currentOperation) return;
      setError(reason instanceof Error ? reason.message : "שגיאה לא ידועה");
    } finally {
      if (operation.current === currentOperation) setBusy(false);
    }
  }, []);

  const start = useCallback(() => {
    lastAction.current = startInterview;
    void run(lastAction.current);
  }, [run]);

  const answer = useCallback(
    (content: string) => {
      const sessionId = turn?.session_id;
      if (!sessionId) return;
      // Echo the answer immediately. A turn is a full model generation, and
      // waiting to render it makes the interface feel like it dropped the
      // input rather than that it is thinking.
      setTurn((current) =>
        current
          ? {
              ...current,
              turns: [
                ...current.turns,
                {
                  role: "user",
                  content,
                  question: null,
                  options: [],
                  recommendation: null,
                },
              ],
              // Retire the buttons with the question they belonged to, so the
              // boss cannot answer the same question twice while it is in
              // flight.
              question: null,
            }
          : current,
      );
      lastAction.current = () => answerInterview(sessionId, content);
      void run(lastAction.current);
    },
    [run, turn?.session_id],
  );

  const end = useCallback(async () => {
    const sessionId = turn?.session_id;
    if (!sessionId) return;
    // Awaited rather than fired and forgotten: the caller navigates to the
    // management area on the strength of this, and that area reads the
    // profile this call is what writes. Leaving first would race it and
    // land on the interview again.
    await run(() => endInterview(sessionId));
  }, [run, turn?.session_id]);

  const reset = useCallback(() => {
    operation.current += 1;
    window.localStorage.removeItem(STORAGE_KEY);
    setTurn(null);
    setError(null);
    lastAction.current = null;
  }, []);

  const retry = useCallback(() => {
    if (lastAction.current) void run(lastAction.current);
  }, [run]);

  // On load, resume the stored session so a refresh continues the interview.
  useEffect(() => {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    const timer = window.setTimeout(() => {
      if (stored) {
        void run(async () => {
          try {
            return await resumeInterview(stored);
          } catch (reason) {
            window.localStorage.removeItem(STORAGE_KEY);
            throw reason;
          }
        });
      }
      else setBusy(false);
    }, 0);
    return () => {
      window.clearTimeout(timer);
      operation.current += 1;
    };
  }, [run]);

  return { turn, busy, error, start, answer, end, reset, retry };
}
