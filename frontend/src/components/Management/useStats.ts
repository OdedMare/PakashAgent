"use client";

import { useEffect, useState } from "react";

import { scheduleStats } from "@/services/api";
import type { ShiftStats } from "@/types";

import type { DateRange } from "./statsRange";

interface Outcome {
  /** The question this answers, so an answer is never shown under a
   *  different one's heading. */
  key: string;
  stats: ShiftStats | null;
  error: string;
}

/** The numbers for whatever the panel is filtered to.
 *
 *  With no filter the overview's own stats are returned and nothing is
 *  fetched: they describe the period on the board and arrived with it, so
 *  they cannot be a refresh behind it. Any other span, or one person, is a
 *  question the overview did not answer and is asked of the server — never
 *  worked out here from the rows on screen, for the reason `Stats` gives: a
 *  second implementation of the count is how a tile comes to disagree with
 *  the warning beneath it.
 *
 *  `base` is a dependency on purpose. The overview is re-read after every
 *  write, so a new `base` is the signal that the schedule moved, and a
 *  filtered view that ignored it would keep showing last minute's week. That
 *  refetch is silent — same question, so the numbers on screen stay put
 *  until the new ones replace them. */
export function useStats(
  base: ShiftStats,
  range: DateRange | null,
  employee: string,
  filtered: boolean,
): { stats: ShiftStats | null; loading: boolean; error: string } {
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const start = range?.start ?? "";
  const end = range?.end ?? "";
  const key = filtered && start && end ? `${start}|${end}|${employee}` : "";

  useEffect(() => {
    if (!key) return;
    // A slow answer to a question the manager has already moved on from
    // must not land on top of the one they are now looking at.
    let stale = false;
    scheduleStats(start, end, employee)
      .then((stats) => {
        if (!stale) setOutcome({ key, stats, error: "" });
      })
      .catch((reason: unknown) => {
        if (stale) return;
        const error =
          reason instanceof Error ? reason.message : "לא ניתן לטעון את הנתונים";
        setOutcome({ key, stats: null, error });
      });
    return () => {
      stale = true;
    };
  }, [key, start, end, employee, base]);

  if (!filtered) return { stats: base, loading: false, error: "" };
  // Filtered, but to nothing yet — a range with one end still empty.
  if (!key) return { stats: null, loading: false, error: "" };
  if (outcome?.key === key) {
    return { stats: outcome.stats, loading: false, error: outcome.error };
  }
  // The previous answer stays up, dimmed, while the next one is on its way:
  // a panel that blanks on every arrow press is harder to read than one
  // whose numbers change in place.
  return { stats: outcome?.stats ?? null, loading: true, error: "" };
}
