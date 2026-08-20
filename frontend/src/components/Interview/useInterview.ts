"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  answerInterview,
  continueInterview,
  finishInterview,
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
  /** True once the boss has asked to stop and the agent came back still
   *  asking. It is what turns `turn.gaps` from a quiet fact about the draft
   *  into the thing on screen: before the request, listing what is missing
   *  on the second question of a twenty-one-question interview is noise. */
  blocked: boolean;
  start: () => void;
  answer: (content: string) => void;
  /** Stop here and keep what has been said. Completes the interview, or —
   *  when a schedule cannot be built from it yet — asks about the gaps. */
  finish: () => void;
  /** Reopen a finished interview and go on adding to it. */
  extend: () => void;
  reset: () => void;
  retry: () => void;
}

export function useInterview(): InterviewState {
  const [turn, setTurn] = useState<InterviewTurn | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // Whether the last attempt to stop early came back still asking. See
  // `blocked` on the state above for why this is not simply `turn.gaps`.
  const [blocked, setBlocked] = useState(false);
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

  const finish = useCallback(() => {
    const sessionId = turn?.session_id;
    if (!sessionId) return;
    // Cleared before the call, so a second attempt after the gaps were
    // closed does not render the previous refusal while it is in flight.
    setBlocked(false);
    lastAction.current = () =>
      run(async () => {
        const next = await finishInterview(sessionId);
        // The server decides whether stopping here was possible. A turn that
        // comes back still asking means it was not, and that is the only
        // thing that puts the gaps on screen.
        setBlocked(next.status !== "complete");
        return next;
      });
    void lastAction.current();
  }, [run, turn?.session_id]);

  const extend = useCallback(() => {
    setBlocked(false);
    lastAction.current = () => run(continueInterview);
    void lastAction.current();
  }, [run]);

  const reset = useCallback(() => {
    window.localStorage.removeItem(STORAGE_KEY);
    setTurn(null);
    setError(null);
    setBlocked(false);
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

  return {
    turn,
    busy,
    error,
    blocked,
    start,
    answer,
    finish,
    extend,
    reset,
    retry,
  };
}
