"use client";

import { useCallback, useEffect, useState } from "react";

import { localToday } from "@/components/Board/dates";
import { rangeOf, showsToday, stepFocus, type BoardView } from "@/components/Board/views";
import { complexBoard } from "@/services/api";
import type { ComplexBoard } from "@/types";

/** The combined board's data: every משמרת of the מכלול over the span the
 *  view draws, read in one call (`GET /api/complex/board`). The anchor and
 *  the four widths are the board's own (`Board/views.ts`), so the arrows,
 *  "היום" and the view switch behave exactly as they do inside a משמרת.
 *
 *  Nothing here writes — a change is made inside the משמרת, with its
 *  commander's powers there (D43). */
export function useCommanderBoard() {
  const [focus, setFocus] = useState(localToday);
  const [view, setView] = useState<BoardView>("week");
  const [board, setBoard] = useState<ComplexBoard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reloads, setReloads] = useState(0);
  const { start, end } = rangeOf(view, focus);

  useEffect(() => {
    let cancelled = false;
    complexBoard(start, end)
      .then((next) => {
        if (cancelled) return;
        setBoard(next);
        setError(null);
      })
      .catch((reason) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "שגיאה לא ידועה");
      });
    return () => {
      cancelled = true;
    };
  }, [start, end, reloads]);

  const today = localToday();
  return {
    view,
    focus,
    start,
    end,
    board,
    error,
    isCurrent: showsToday(view, focus, today),
    setView,
    reload: useCallback(() => setReloads((n) => n + 1), []),
    previous: () => setFocus((current) => stepFocus(view, current, -1)),
    next: () => setFocus((current) => stepFocus(view, current, 1)),
    goToToday: () => setFocus(localToday()),
  };
}

export type CommanderBoardState = ReturnType<typeof useCommanderBoard>;
