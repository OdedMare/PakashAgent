"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  applyChange,
  briefManager,
  deleteConstraint,
  downloadSchedule,
  generateSchedule,
  moveAssignment,
  proposeChange,
  publishSchedule,
  scheduleOverview,
  setConstraint,
  unpublishSchedule,
} from "@/services/api";
import type {
  Briefing,
  BriefingTrigger,
  ManagementOverview,
  Operation,
  Proposal,
} from "@/types";

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
  /** What the agent said on its own initiative, or null before it has
   *  spoken. A quiet briefing is still a briefing — the UI decides how
   *  loudly to render it (D15). */
  briefing: Briefing | null;
  briefing_busy: boolean;
  /** Ask the agent to speak. Called on open, after writes, and before
   *  publishing; safe to call at any time and never throws. */
  brief: (trigger: BriefingTrigger) => Promise<Briefing | null>;
  dismissBriefing: () => void;
  refresh: () => Promise<void>;
  generate: (input: {
    starts_on?: string;
    ends_on?: string;
    instructions?: string;
  }) => Promise<void>;
  publish: (scheduleId: string, published: boolean) => Promise<void>;
  /** Download the period as `.xlsx` (D17). */
  exportSchedule: (scheduleId: string) => Promise<void>;
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

/** How often the agent takes the long look at an idle control room. */
const PERIODIC_BRIEFING_MS = 30 * 60 * 1000;

export function useManagement(): ManagementState {
  const [overview, setOverview] = useState<ManagementOverview | undefined>(
    undefined,
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [briefing, setBriefing] = useState<Briefing | null>(null);
  const [briefingBusy, setBriefingBusy] = useState(false);
  // The headlines already shown this sitting, sent back so the agent does not
  // open with something the manager just read. Deliberately a ref and not
  // state: it is remembered, never rendered, and putting it in state would
  // re-run the effects that produce it.
  const spoken = useRef<string[]>([]);

  const refresh = useCallback(async () => {
    const next = await scheduleOverview().catch(() => null);
    if (next) setOverview(next);
  }, []);

  /** Ask the agent to speak (D15).
   *
   *  Never throws and never sets `error`: a briefing is the agent's own
   *  initiative, so a failure means it has nothing to say — not that the
   *  manager's action failed. It has its own `busy` flag for the same
   *  reason, so a slow briefing does not disable the calendar around it.
   *
   *  A quiet briefing is kept rather than discarded. "נראה תקין" said once
   *  after generating a week is worth reading; it is the UI that decides to
   *  render it small. */
  const brief = useCallback(async (trigger: BriefingTrigger) => {
    setBriefingBusy(true);
    try {
      const said = await briefManager(trigger, spoken.current);
      if (said.headline) {
        spoken.current = [...spoken.current, said.headline].slice(-8);
      }
      setBriefing(said);
      return said;
    } catch {
      return null;
    } finally {
      setBriefingBusy(false);
    }
  }, []);

  const dismissBriefing = useCallback(() => setBriefing(null), []);

  /** Run a write, surface its Hebrew error, and re-read the world after. */
  const run = useCallback(
    async <T,>(action: () => Promise<T>): Promise<T | null> => {
      setBusy(true);
      setError(null);
      try {
        const result = await action();
        await refresh();
        // Every write funnels through here, so this one line is what makes
        // the agent react to a generated week, an applied change, a recorded
        // constraint and a ruled-on request alike. Deliberately not awaited:
        // the manager gets their updated calendar immediately and the
        // agent's remark arrives when it arrives.
        void brief("changed");
        return result;
      } catch (reason) {
        setError(reason instanceof Error ? reason.message : "שגיאה לא ידועה");
        return null;
      } finally {
        setBusy(false);
      }
    },
    [refresh, brief],
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

  /** Publish or withdraw a period.
   *
   *  Publishing briefs *first* and waits for it: this is the last cheap
   *  moment to catch an unstaffed slot, and a remark that arrived after the
   *  team already had the schedule would be a report rather than a warning.
   *  It still does not gate anything — the publish runs whatever the agent
   *  says, because warnings inform and never block
   *  ([D3](../../../docs/DECISIONS.md#d3--the-agent-decides-code-only-audits-)). */
  const publish = useCallback(
    async (scheduleId: string, published: boolean) => {
      if (published) await brief("publishing");
      await run(() =>
        published ? publishSchedule(scheduleId) : unpublishSchedule(scheduleId),
      );
    },
    [run, brief],
  );

  /** Hand the period out as a file.
   *
   *  Not routed through `run()`: that refetches the world and re-briefs the
   *  agent after every call, and a download changes nothing for either to
   *  react to. It still surfaces its Hebrew error the same way, because a
   *  failed download is otherwise completely silent. */
  const exportSchedule = useCallback(async (scheduleId: string) => {
    setBusy(true);
    setError(null);
    try {
      await downloadSchedule(scheduleId);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "שגיאה לא ידועה");
    } finally {
      setBusy(false);
    }
  }, []);

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
        // The opening remark, after the overview rather than beside it: the
        // calendar is what the manager came for, and the agent's greeting
        // must never be what they are waiting on.
        if (!cancelled) void brief("opened");
      });
    return () => {
      cancelled = true;
    };
  }, [brief]);

  /** The long look, for a control room left open.
   *
   *  `periodic` is the only trigger nothing prompts — it exists so patterns
   *  across periods ("רון עשה ארבעה סופי שבוע ברצף") get noticed at all,
   *  since no single action reveals them. Half an hour is chosen to be
   *  rarer than the manager's own rhythm: this speaks unasked, and a thing
   *  that speaks unasked too often stops being read. */
  useEffect(() => {
    const timer = window.setInterval(
      () => void brief("periodic"),
      PERIODIC_BRIEFING_MS,
    );
    return () => window.clearInterval(timer);
  }, [brief]);

  return {
    overview,
    busy,
    error,
    proposal,
    briefing,
    briefing_busy: briefingBusy,
    brief,
    dismissBriefing,
    refresh,
    generate,
    publish,
    exportSchedule,
    propose,
    confirm,
    dismissProposal,
    move,
    addConstraint,
    removeConstraint,
    clearError,
  };
}
