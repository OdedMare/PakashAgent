"use client";

import { useCallback, useEffect, useState } from "react";

import {
  assignDuty, cancelDuty, createDutyType, deleteDutyType, dutyBoard, dutyRoster,
  updateDutyType,
} from "@/services/api";
import type { DutyBoard, DutyConflict, DutyRosterTeam, DutyType } from "@/types";

/** The מכלול's duties over the range on screen, the soldiers to pick from,
 *  and every write the duties page makes. Every write re-reads the board,
 *  like the management area does: the server is the only count of seats. */
export function useDuties(start: string, end: string) {
  const [board, setBoard] = useState<DutyBoard | null>(null);
  const [roster, setRoster] = useState<DutyRosterTeam[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [reloads, setReloads] = useState(0);

  useEffect(() => {
    let cancelled = false;
    dutyBoard(start, end)
      .then((next) => {
        if (cancelled) return;
        setBoard(next);
        setError(null);
      })
      .catch((reason) => { if (!cancelled) setError(message(reason)); });
    return () => { cancelled = true; };
  }, [start, end, reloads]);
  useEffect(() => {
    let cancelled = false;
    dutyRoster()
      .then((next) => { if (!cancelled) setRoster(next); })
      .catch((reason) => { if (!cancelled) setError(message(reason)); });
    return () => { cancelled = true; };
  }, []);
  const reload = useCallback(() => setReloads((n) => n + 1), []);

  const run = async <T,>(write: () => Promise<T>): Promise<T | null> => {
    setBusy(true);
    try {
      const result = await write();
      setError(null);
      reload();
      return result;
    } catch (reason) {
      setError(message(reason));
      return null;
    } finally {
      setBusy(false);
    }
  };

  return {
    board, roster, error, busy, reload,
    clearError: () => setError(null),
    createType: (input: { name: string; seats: number; weight: number; days: string[] }) =>
      run(() => createDutyType(input)),
    updateType: (id: string, patch: Partial<Omit<DutyType, "id">>) => run(() => updateDutyType(id, patch)),
    deleteType: (id: string) => run(() => deleteDutyType(id)),
    /** The shifts the new duty blocks, or null when it was refused. */
    assign: async (input: Parameters<typeof assignDuty>[0]): Promise<DutyConflict[] | null> => {
      const result = await run(() => assignDuty(input));
      return result ? result.conflicts : null;
    },
    cancel: (id: string) => run(() => cancelDuty(id)),
  };
}

function message(reason: unknown): string {
  return reason instanceof Error ? reason.message : "הפעולה נכשלה";
}

/** Weekday keys as the server stores them, indexed by `Date.getUTCDay()`. */
export const WEEKDAY_KEYS = ["ראשון", "שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת"];

export function weekdayKey(iso: string): string {
  return WEEKDAY_KEYS[new Date(`${iso}T00:00:00Z`).getUTCDay()];
}

export function runsOn(type: DutyType, iso: string): boolean {
  return !type.days.length || type.days.includes(weekdayKey(iso));
}
