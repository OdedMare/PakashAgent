"use client";

import { useCallback, useEffect, useState } from "react";

import {
  applyChange,
  deleteConstraint,
  generateSchedule,
  moveAssignment,
  proposeChange,
  publishSchedule,
  scheduleOverview,
  setConstraint,
  unpublishSchedule,
} from "@/services/api";
import type { ManagementOverview, Operation, Proposal } from "@/types";

/** The management area's server state.
 *
 *  Everything is re-read from `/api/schedule/overview` after any write rather
 *  than patched locally. The schedule, its warnings, the constraints, and the
 *  change log all move together — a locally patched grid whose warnings were
 *  computed by the server before the change would show the manager a stale
 *  audit next to a fresh schedule, which is worse than a brief spinner.
 *
 *  `undefined` means "not asked yet" and `null` would mean "nothing there";
 *  the distinction keeps the empty state from flashing during the first load.
 */
export interface ManagementState {
  overview: ManagementOverview | undefined;
  busy: boolean;
  error: string | null;
  /** The agent's pending proposal, awaiting the manager's confirmation.
   *  Nothing has been applied while this is set — that is the whole point of
   *  the two-step contract (D8). */
  proposal: Proposal | null;
  refresh: () => Promise<void>;
  generate: (input: {
    starts_on?: string;
    ends_on?: string;
    instructions?: string;
  }) => Promise<void>;
  publish: (scheduleId: string, published: boolean) => Promise<void>;
  propose: (request: string, reason?: string) => Promise<Proposal | null>;
  confirm: (reason: string) => Promise<void>;
  dismissProposal: () => void;
  move: (input: {
    assignment_id: string;
    shift_name: string;
    slot_date: string;
    reason: string;
  }) => Promise<void>;
  addConstraint: (input: {
    employee: string;
    constraint_date: string;
    shift_name?: string;
    reason?: string;
    source?: string;
  }) => Promise<void>;
  removeConstraint: (rowId: string) => Promise<void>;
  clearError: () => void;
}

export function useManagement(): ManagementState {
  const [overview, setOverview] = useState<ManagementOverview | undefined>(
    undefined,
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [proposal, setProposal] = useState<Proposal | null>(null);

  const refresh = useCallback(async () => {
    const next = await scheduleOverview().catch(() => null);
    if (next) setOverview(next);
  }, []);

  /** Run a write, surface its Hebrew error, and re-read the world after. */
  const run = useCallback(
    async <T,>(action: () => Promise<T>): Promise<T | null> => {
      setBusy(true);
      setError(null);
      try {
        const result = await action();
        await refresh();
        return result;
      } catch (reason) {
        setError(reason instanceof Error ? reason.message : "שגיאה לא ידועה");
        return null;
      } finally {
        setBusy(false);
      }
    },
    [refresh],
  );

  const generate = useCallback(
    async (input: {
      starts_on?: string;
      ends_on?: string;
      instructions?: string;
    }) => {
      await run(() => generateSchedule(input));
    },
    [run],
  );

  const publish = useCallback(
    async (scheduleId: string, published: boolean) => {
      await run(() =>
        published ? publishSchedule(scheduleId) : unpublishSchedule(scheduleId),
      );
    },
    [run],
  );

  /** Ask the agent what it would do. Persists nothing.
   *
   *  The result is held in `proposal` until the manager confirms or dismisses
   *  it. A proposal that comes back with `needs_reason` is the agent asking
   *  why — it carries no operations, and the composer shows the question. */
  // Read out of the overview rather than reached for inside the callback:
  // the dependency the compiler infers from `overview?.schedule?.id` is the
  // whole `overview`, which would not match the narrower one declared here
  // and costs the memoization entirely.
  const scheduleId = overview?.schedule?.id;

  const propose = useCallback(
    async (request: string, reason?: string) => {
      setBusy(true);
      setError(null);
      try {
        const result = await proposeChange({
          request,
          reason: reason ?? "",
          schedule_id: scheduleId,
        });
        setProposal(result);
        return result;
      } catch (reason_) {
        setError(reason_ instanceof Error ? reason_.message : "שגיאה לא ידועה");
        return null;
      } finally {
        setBusy(false);
      }
    },
    [scheduleId],
  );

  /** Apply the pending proposal with the manager's reason attached. */
  const confirm = useCallback(
    async (reason: string) => {
      if (!proposal) return;
      const applied = await run(() =>
        applyChange({
          schedule_id: proposal.schedule_id,
          operations: proposal.operations as Operation[],
          reason,
          agent_reason: proposal.agent_reason,
        }),
      );
      if (applied) setProposal(null);
    },
    [proposal, run],
  );

  const dismissProposal = useCallback(() => setProposal(null), []);

  const move = useCallback(
    async (input: {
      assignment_id: string;
      shift_name: string;
      slot_date: string;
      reason: string;
    }) => {
      await run(() => moveAssignment(input));
    },
    [run],
  );

  const addConstraint = useCallback(
    async (input: {
      employee: string;
      constraint_date: string;
      shift_name?: string;
      reason?: string;
      source?: string;
    }) => {
      await run(() => setConstraint(input));
    },
    [run],
  );

  const removeConstraint = useCallback(
    async (rowId: string) => {
      await run(() => deleteConstraint(rowId));
    },
    [run],
  );

  const clearError = useCallback(() => setError(null), []);

  // `cancelled` guards the unmount race: React's development double-mount
  // makes a component gone before the first answer arrives routine rather
  // than theoretical.
  useEffect(() => {
    let cancelled = false;
    scheduleOverview()
      .catch(() => null)
      .then((next) => {
        if (!cancelled && next) setOverview(next);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return {
    overview,
    busy,
    error,
    proposal,
    refresh,
    generate,
    publish,
    propose,
    confirm,
    dismissProposal,
    move,
    addConstraint,
    removeConstraint,
    clearError,
  };
}
