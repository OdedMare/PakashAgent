"use client";

import { useEffect, useState } from "react";

import { rotationPreview } from "@/services/api";
import type { RotationWeekend } from "@/types";

type Cycles = Partial<Record<"round" | "triplet", RotationWeekend[]>>;

/** The server's view of the coming weekends for the rotation on screen.
 *
 *  Re-asked a moment after the manager stops typing, and the stale request
 *  is aborted, so the strip always answers the latest rows. A row that
 *  would not save comes back as `error` rather than an exception. */
export function useRotationPreview(workplace: Record<string, unknown>, shifts: Record<string, unknown>[]) {
  const [cycles, setCycles] = useState<Cycles>({});
  const [error, setError] = useState("");
  // The rows the strip last answered; anything newer is still on its way.
  const [answered, setAnswered] = useState("");
  const key = JSON.stringify([workplace, shifts]);

  useEffect(() => {
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      const [place, rows] = JSON.parse(key) as [Record<string, unknown>, Record<string, unknown>[]];
      rotationPreview({ workplace: place, shifts: rows, weeks: 8 }, controller.signal)
        .then((result) => { setCycles(result.cycles); setError(result.error); })
        .catch((reason) => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "התצוגה המקדימה אינה זמינה"); })
        .finally(() => { if (!controller.signal.aborted) setAnswered(key); });
    }, 400);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [key]);

  return { cycles, error, loading: answered !== key };
}
