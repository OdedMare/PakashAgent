"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { pendingRequests } from "@/services/api";
import type { ConstraintRequestRow } from "@/types";

/** Pending constraint requests, kept fresh while the manager is on screen.
 *
 *  Lifted out of `RequestInbox` so the drawer tab can carry the count and the
 *  workspace can announce a new submission without the inbox being open.
 *  `reload` is what `useLiveInbox` calls the moment an employee submits; the
 *  15-second poll stays underneath as the backstop for a dropped stream.
 *  Nothing is sent anywhere (D16 — a mark, not a message): the push only
 *  reaches the manager's own open screen.
 *
 *  `arrivals` are rows that appeared *after* the first load. Requests already
 *  waiting when the screen opened are counted on the badge but not announced:
 *  they are not news, and a pop-up on every visit would train the manager to
 *  dismiss it unread. Nor is a request that lands while the manager is
 *  already `watching` the inbox — it is on screen, and announcing it later
 *  would pop up something they have already seen. */
export function useConstraintRequests(watching: boolean) {
  const [rows, setRows] = useState<ConstraintRequestRow[]>([]);
  const [arrivals, setArrivals] = useState<ConstraintRequestRow[]>([]);
  // Every id ever seen, not just the current pending set: a request that was
  // settled here and is still in flight on the server must not re-announce.
  const known = useRef<Set<string> | null>(null);
  // Decided here; a poll already in flight may still list them as pending.
  const settled = useRef(new Set<string>());
  // Read inside the poll, which outlives any one render.
  const watchingRef = useRef(watching);
  useEffect(() => {
    watchingRef.current = watching;
  }, [watching]);

  const load = useCallback(async () => {
    const next = await pendingRequests().catch(() => null);
    if (!next) return;
    setRows(next.filter((row) => !settled.current.has(row.id)));
    if (known.current === null) {
      known.current = new Set(next.map((row) => row.id));
      return;
    }
    const seen = known.current;
    const fresh = next.filter((row) => !seen.has(row.id) && !settled.current.has(row.id));
    fresh.forEach((row) => seen.add(row.id));
    if (fresh.length && !watchingRef.current) setArrivals((current) => [...current, ...fresh]);
  }, []);

  useEffect(() => {
    const refresh = () => void load();
    const first = window.setTimeout(refresh, 0);
    const timer = window.setInterval(refresh, 15000);
    // Coming back to the tab is the moment a stale count is most misleading.
    const onVisible = () => {
      if (document.visibilityState === "visible") refresh();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      window.clearTimeout(first);
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [load]);

  /** Drop a decided row locally so the inbox does not flash on reload. */
  const settle = useCallback((id: string) => {
    settled.current.add(id);
    setRows((current) => current.filter((row) => row.id !== id));
    setArrivals((current) => current.filter((row) => row.id !== id));
  }, []);

  const dismissArrivals = useCallback(() => setArrivals([]), []);

  const reload = useCallback(() => void load(), [load]);

  return { rows, arrivals, settle, dismissArrivals, reload };
}
