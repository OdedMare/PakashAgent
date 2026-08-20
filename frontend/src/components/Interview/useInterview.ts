"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  answerInterview,
  endInterview,
  resumeInterview,
  startInterview,
} from "@/services/api";
import type { InterviewTurn } from "@/types";

/** The interview lives server-side; this holds only the session id, so a
 *  refresh resumes the same conversation rather than starting a second one.
 *  Resuming replays the stored question and costs no model call. */
const STORAGE_KEY = "pakash.interview.session";

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
  // What to re-run when the boss presses "retry" on a failed turn.
  const lastAction = useRef<(() => Promise<void>) | null>(null);

  const run = useCallback(async (action: () => Promise<InterviewTurn>) => {
    setBusy(true);
    setError(null);
    try {
      const next = await action();
      setTurn(next);
      window.localStorage.setItem(STORAGE_KEY, next.session_id);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "שגיאה לא ידועה");
    } finally {
      setBusy(false);
    }
  }, []);

  const start = useCallback(() => {
    lastAction.current = () => run(startInterview);
    void lastAction.current();
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
      lastAction.current = () => run(() => answerInterview(sessionId, content));
      void lastAction.current();
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
    window.localStorage.removeItem(STORAGE_KEY);
    setTurn(null);
    setError(null);
    lastAction.current = null;
  }, []);

  const retry = useCallback(() => {
    void lastAction.current?.();
  }, []);

  // On load, resume the stored session so a refresh continues the interview.
  useEffect(() => {
    let cancelled = false;
    const stored = window.localStorage.getItem(STORAGE_KEY);
    // Resolved rather than returned early even when there is nothing stored,
    // so `busy` is always cleared from a callback. Clearing it synchronously
    // in the effect body cascades an extra render on every first paint.
    const resumed = stored
      ? resumeInterview(stored).then((next) => {
          if (!cancelled) setTurn(next);
        })
      : Promise.resolve();
    resumed
      .catch(() => {
        // A session the server no longer has (a dropped database, a cleared
        // schema) must not strand the boss on an error screen forever.
        window.localStorage.removeItem(STORAGE_KEY);
      })
      .finally(() => {
        if (!cancelled) setBusy(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return { turn, busy, error, start, answer, end, reset, retry };
}
