"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  applyChange,
  askAgent,
  assignEmployee,
  blankSchedule,
  briefManager,
  cancelScheduleGeneration,
  deleteConstraint,
  downloadSchedule,
  generateSchedule,
  generateScheduleDay,
  GenerationStoppedError,
  moveAssignment,
  ProfileIncompleteError,
  proposeChange,
  publishSchedule,
  resumeScheduleGeneration,
  scheduleOverview,
  setConstraint,
  simulateChange,
  unassignEmployee,
  unpublishSchedule,
  updateProfile,
} from "@/services/api";
import type {
  AgentAnswer,
  Briefing,
  BriefingTrigger,
  GenerationProgress,
  ManagementOverview,
  Operation,
  Proposal,
  Schedule,
  Simulation,
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
/** A refused build, as the UI renders it.
 *
 *  `gaps` are the interview's own required-topic lines and `blocks` says what
 *  each one costs. Both come from the backend rather than being written here:
 *  one definition of "missing" lives in `bl/interview.py`, and a second copy
 *  in the client would drift from the gate that actually refuses. */
export interface ProfileGaps {
  message: string;
  gaps: string[];
  blocks: string[];
}

export interface ManagementState {
  overview: ManagementOverview | undefined;
  /** A short write is in flight. Gates the board's own controls.
   *
   *  **Building a period is deliberately not one of these.** A build runs for
   *  minutes and its days land one at a time; holding the whole area disabled
   *  for its duration is what left a manager unable to place a single shift —
   *  or to reach the button that stops it — while the agent worked, and a
   *  build that never finished disabled the area forever. Generation reports
   *  through `generating` instead, and the board stays writable throughout
   *  (D18): what the manager places by hand becomes a pin the agent fills
   *  around, exactly as it does on a single-day rebuild. */
  busy: boolean;
  error: string | null;
  generation: GenerationProgress | null;
  /** A build is running and this browser is watching it. */
  generating: boolean;
  resumeGeneration: (scheduleId: string) => Promise<void>;
  /** Stop waiting on a build, keeping every day already finished.
   *
   *  The manager's way out, and the reason polling is allowed to end at all:
   *  with no model timeout configured, a hung server and a slow one look
   *  identical from here, and only a person can say whether anyone is still
   *  waiting. */
  cancelGeneration: () => Promise<void>;
  /** Set when a build was refused because the interview never taught the
   *  shift vocabulary, and cleared by any later success.
   *
   *  Kept apart from `error` because it is not the same kind of thing. An
   *  error is read and dismissed; this names what is missing and has a way
   *  forward attached, and rendering it as one more red line would hide the
   *  only part the manager can act on. */
  gaps: ProfileGaps | null;
  dismissGaps: () => void;
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
    required_assignments?: import("@/types").RequiredAssignment[];
  }) => Promise<void>;
  /** Rebuild one date in the current draft from instructions on the board. */
  generateDay: (input: {
    schedule_id: string;
    date: string;
    instructions?: string;
  }) => Promise<void>;
  /** Open an empty period to fill in by hand (D18). Calls no model. */
  openBlank: (input: { starts_on?: string; ends_on?: string }) => Promise<void>;
  /** Place one person on one slot, by hand (D18). Writes immediately.
   *
   *  `schedule_id` is the period the click happened on. The board always
   *  sends it: without one the server writes to whichever period covers
   *  today, which refuses every placement made on any other week. */
  assign: (input: {
    shift_name: string;
    slot_date: string;
    employee: string;
    reason?: string;
    schedule_id?: string;
  }) => Promise<void>;
  /** Take one person off a slot, by hand (D18). */
  unassign: (input: {
    assignment_id: string;
    reason?: string;
    schedule_id?: string;
  }) => Promise<void>;
  publish: (scheduleId: string, published: boolean) => Promise<void>;
  /** Download the period as `.xlsx` (D17). */
  exportSchedule: (scheduleId: string) => Promise<void>;
  propose: (request: string, reason?: string) => Promise<Proposal | null>;
  confirm: (reason: string) => Promise<void>;
  dismissProposal: () => void;
  /** What the agent found when asked a question. Carries no operations, so
   *  there is nothing here that could be applied (D15). */
  answer: AgentAnswer | null;
  answer_busy: boolean;
  /** Ask the agent about the schedule. Reads only; writes nothing. */
  ask: (request: string) => Promise<AgentAnswer | null>;
  dismissAnswer: () => void;
  /** A change the manager is only considering. Persists nothing until it is
   *  approved, and approving runs the ordinary `apply` path with a reason. */
  simulation: Simulation | null;
  simulate: (operations: Operation[]) => Promise<Simulation | null>;
  approveSimulation: (reason: string) => Promise<void>;
  dismissSimulation: () => void;
  move: (input: {
    assignment_id: string;
    shift_name: string;
    slot_date: string;
    reason: string;
    schedule_id?: string;
  }) => Promise<void>;
  /** Tell the hook which period the manager is looking at.
   *
   *  The overview hands over the *current* period, and the board may be
   *  showing another week entirely. Everything that targets "the schedule"
   *  — the agent's proposals, its answers, a simulation — followed the
   *  overview and so answered about the wrong week whenever the manager had
   *  paged away. The board reports what it is rendering, and this is what
   *  the rest of the area then aims at. */
  focusPeriod: (scheduleId: string) => void;
  addConstraint: (input: {
    employee: string;
    constraint_date: string;
    shift_name?: string;
    available?: boolean;
    start_time?: string;
    end_time?: string;
    is_hard?: boolean;
    reason?: string;
    source?: string;
  }) => Promise<void>;
  removeConstraint: (rowId: string) => Promise<void>;
  saveProfile: (input: {
    employees?: Record<string, unknown>[];
    shifts?: Record<string, unknown>[];
  }) => Promise<void>;
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
  const [generation, setGeneration] = useState<GenerationProgress | null>(null);
  // A build is running and this browser is watching it. Kept apart from
  // `busy` on purpose -- see `ManagementState.busy`. The board stays
  // writable while this is true.
  const [generating, setGenerating] = useState(false);
  // The poll in flight, so it can be stopped: by the manager pressing stop,
  // or by a second build replacing it. A ref rather than state because
  // nothing renders it and re-rendering on it would restart the effects that
  // produced it.
  const watching = useRef<AbortController | null>(null);
  // Which period the current watch belongs to. Read when stopping, and the
  // overview cannot be trusted for it: a build opens a period the overview
  // has not been re-read for yet.
  const generatingId = useRef<string>("");
  // The period the manager is actually looking at, reported by the board.
  // The overview only ever hands over the *current* one, so everything that
  // aimed at "the schedule" aimed at the wrong week the moment the manager
  // paged away — the agent answered about a week they were not looking at,
  // and every hand-write was refused outright because the slot it named does
  // not exist in the period covering today. Empty until the board has
  // rendered; the overview is the fallback.
  const [focused, setFocused] = useState("");
  const focusPeriod = useCallback((id: string) => setFocused(id), []);

  /** Stamp the period on a hand-write that did not name one.
   *
   *  The board always names it. This is the safety net for any caller that
   *  does not, and it is what makes "no id" mean "the week on screen"
   *  rather than "whatever covers today". */
  const withPeriod = useCallback(
    <T extends { schedule_id?: string }>(input: T): T =>
      input.schedule_id ? input : { ...input, schedule_id: focused },
    [focused],
  );
  const [gaps, setGaps] = useState<ProfileGaps | null>(null);
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [briefing, setBriefing] = useState<Briefing | null>(null);
  const [briefingBusy, setBriefingBusy] = useState(false);
  const [answer, setAnswer] = useState<AgentAnswer | null>(null);
  const [answerBusy, setAnswerBusy] = useState(false);
  const [simulation, setSimulation] = useState<Simulation | null>(null);
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

  /** Run a write, surface its Hebrew error, and re-read the world after.
   *
   *  `quiet` suppresses the briefing that normally follows a write. It is
   *  for the manual path (D18), where the manager is placing one person per
   *  click: a model call per cell would make authoring a week by hand the
   *  most expensive thing in the product, and the agent would be remarking
   *  on a half-built grid it is watching being typed. The audit still runs
   *  on every one of those writes — it is pure arithmetic and costs nothing
   *  — so the warnings under the calendar stay live throughout. The agent
   *  catches up on the next ordinary write, on publish, or when the manager
   *  asks. */
  const run = useCallback(
    async <T,>(
      action: () => Promise<T>,
      options?: { quiet?: boolean },
    ): Promise<T | null> => {
      setBusy(true);
      setError(null);
      try {
        const result = await action();
        // A build that succeeded answers the refusal, whatever filled the
        // gap in the meantime.
        setGaps(null);
        await refresh();
        // Every write funnels through here, so this one line is what makes
        // the agent react to a generated week, an applied change, a recorded
        // constraint and a ruled-on request alike. Deliberately not awaited:
        // the manager gets their updated calendar immediately and the
        // agent's remark arrives when it arrives.
        if (!options?.quiet) void brief("changed");
        return result;
      } catch (reason) {
        // Every write funnels through here, so both building buttons get the
        // resumable refusal handled once rather than each growing its own
        // copy of the same branch.
        if (reason instanceof ProfileIncompleteError) {
          setGaps({
            message: reason.message,
            gaps: reason.gaps,
            blocks: reason.blocks,
          });
          return null;
        }
        setError(reason instanceof Error ? reason.message : "שגיאה לא ידועה");
        return null;
      } finally {
        setBusy(false);
      }
    },
    [refresh, brief],
  );

  /** Watch a build to its end, leaving the rest of the area usable.
   *
   *  Deliberately **not** `run()`. That helper is for the short writes the
   *  board's own controls wait on, and routing a build through it disabled
   *  every one of them for the length of the build — including the button
   *  that stops it, and including forever when the build never ended.
   *
   *  So this keeps its own flag, refreshes at the end rather than gating on
   *  it, and treats the manager pressing stop as an outcome rather than an
   *  error. Progress arrives from the poll: each day that lands re-renders
   *  the grid under the manager while they keep working on it. */
  const watchGeneration = useCallback(
    async (
      start: (
        onProgress: (schedule: Schedule) => void,
        signal: AbortSignal,
      ) => Promise<Schedule>,
      scheduleId = "",
    ) => {
      // Any earlier watch is stopped first: two pollers on one job would
      // fight over `generation`, and the older one is by definition looking
      // at whatever the manager just moved on from.
      watching.current?.abort();
      const control = new AbortController();
      watching.current = control;
      generatingId.current = scheduleId;
      setGenerating(true);
      setError(null);
      try {
        const schedule = await start((next) => {
          if (control.signal.aborted) return;
          generatingId.current = next.id;
          setGeneration(next.generation);
          // Only ever the period this watch is building. A poll that landed
          // after the manager moved to another period must not swap the
          // board out from under them.
          setOverview((current) =>
            current && (!current.schedule || current.schedule.id === next.id)
              ? { ...current, schedule: next }
              : current,
          );
        }, control.signal);
        // A build that succeeded answers the refusal, whatever filled the
        // gap in the meantime.
        setGaps(null);
        setGeneration(schedule.generation);
        await refresh();
        if (schedule.generation.status === "complete") void brief("changed");
      } catch (reason) {
        // The manager pressed stop. The days already built are on the board
        // and the last poll left the banner saying so; there is no failure
        // here to report.
        if (reason instanceof GenerationStoppedError) return;
        if (reason instanceof ProfileIncompleteError) {
          setGaps({
            message: reason.message,
            gaps: reason.gaps,
            blocks: reason.blocks,
          });
          setGeneration(null);
        } else {
          setError(reason instanceof Error ? reason.message : "שגיאה לא ידועה");
        }
        await refresh();
      } finally {
        if (watching.current === control) {
          watching.current = null;
          setGenerating(false);
        }
      }
    },
    [refresh, brief],
  );

  const generate = useCallback(
    async (input: {
      starts_on?: string;
      ends_on?: string;
      instructions?: string;
      required_assignments?: import("@/types").RequiredAssignment[];
    }) => {
      const totalDays = inclusiveDays(input.starts_on, input.ends_on) ?? 7;
      // Show progress from the click, including the short request that opens
      // the persisted job. Waiting for that response left the board looking
      // idle even though generation had already started.
      setGeneration({
        status: "running",
        current_date: input.starts_on ?? "",
        total_days: totalDays,
        completed_days: 0,
        failed_days: 0,
        days: [],
      });
      await watchGeneration((onProgress, signal) =>
        generateSchedule(input, onProgress, { signal }),
      );
    },
    [watchGeneration],
  );

  const resumeGeneration = useCallback(
    async (scheduleId: string) => {
      await watchGeneration(
        (onProgress, signal) =>
          resumeScheduleGeneration(scheduleId, onProgress, { signal }),
        scheduleId,
      );
    },
    [watchGeneration],
  );

  const generateDay = useCallback(async (input: {
    schedule_id: string;
    date: string;
    instructions?: string;
  }) => {
    setGeneration({
      status: "running",
      current_date: input.date,
      total_days: 1,
      completed_days: 0,
      failed_days: 0,
      days: [],
    });
    await watchGeneration(
      (onProgress, signal) =>
        generateScheduleDay(input, onProgress, { signal }),
      input.schedule_id,
    );
  }, [watchGeneration]);

  /** Stop the build this browser is watching.
   *
   *  Two halves, and both are needed: the server is told so it stops taking
   *  new days, and the poller is aborted so the manager's screen settles
   *  immediately rather than after the model finishes whatever it is on. */
  const cancelGeneration = useCallback(async () => {
    const scheduleId = generatingId.current;
    watching.current?.abort();
    watching.current = null;
    setGenerating(false);
    if (!scheduleId) return;
    try {
      const stopped = await cancelScheduleGeneration(scheduleId);
      setGeneration(stopped.generation);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "שגיאה לא ידועה");
    }
    await refresh();
  }, [refresh]);

  /** Open an empty period for the manager to fill in themselves (D18).
   *
   *  The one schedule-building path with no model on it at all. It *does*
   *  brief afterwards, unlike the per-cell writes below: an empty week is a
   *  state worth one remark, and it happens once rather than forty times. */
  const openBlank = useCallback(
    async (input: { starts_on?: string; ends_on?: string }) => {
      await run(() => blankSchedule(input));
    },
    [run],
  );

  /** Place one person on one slot. Quiet: see `run`. */
  const assign = useCallback(
    async (input: {
      shift_name: string;
      slot_date: string;
      employee: string;
      reason?: string;
      schedule_id?: string;
    }) => {
      await run(() => assignEmployee(withPeriod(input)), { quiet: true });
    },
    [run, withPeriod],
  );

  /** Take one person off a slot. Quiet for the same reason as `assign`. */
  const unassign = useCallback(
    async (input: {
      assignment_id: string;
      reason?: string;
      schedule_id?: string;
    }) => {
      await run(() => unassignEmployee(withPeriod(input)), { quiet: true });
    },
    [run, withPeriod],
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
  const scheduleId = focused || overview?.schedule?.id;

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
          profile_operations: proposal.profile_operations,
          reason,
          agent_reason: proposal.agent_reason,
        }),
      );
      if (applied) setProposal(null);
    },
    [proposal, run],
  );

  const dismissProposal = useCallback(() => setProposal(null), []);

  const saveProfile = useCallback(async (input: {
    employees?: Record<string, unknown>[];
    shifts?: Record<string, unknown>[];
  }) => {
    await run(() => updateProfile(input));
  }, [run]);

  /** Ask the agent about the schedule. **Reads only.**
   *
   *  Separate from `propose` on purpose: a proposal is an answer with a
   *  confirm button attached, and offering one in reply to "who could cover
   *  Saturday" answers something the manager did not ask. The response
   *  carries no operations, so there is nothing here that could be applied.
   *
   *  It does not go through `run()` — nothing was written, so there is
   *  nothing for a refetch or a briefing to react to, and re-reading the
   *  world after a question would make asking cost more than acting. */
  const ask = useCallback(
    async (request: string) => {
      setAnswerBusy(true);
      setAnswer(null);
      setError(null);
      try {
        const found = await askAgent({ request, schedule_id: scheduleId });
        setAnswer(found);
        return found;
      } catch (reason) {
        setError(reason instanceof Error ? reason.message : "שגיאה לא ידועה");
        return null;
      } finally {
        setAnswerBusy(false);
      }
    },
    [scheduleId],
  );

  const dismissAnswer = useCallback(() => setAnswer(null), []);

  /** What a set of operations would do. **Persists nothing.**
   *
   *  Also outside `run()`, and for a stronger reason than `ask`: a
   *  simulation must not refetch, because refetching after a call that
   *  changed nothing would make the screen behave as though it had. */
  const simulate = useCallback(
    async (operations: Operation[]) => {
      setBusy(true);
      setError(null);
      try {
        const result = await simulateChange({
          operations,
          schedule_id: scheduleId,
        });
        setSimulation(result);
        return result;
      } catch (reason) {
        setError(reason instanceof Error ? reason.message : "שגיאה לא ידועה");
        return null;
      } finally {
        setBusy(false);
      }
    },
    [scheduleId],
  );

  /** Approve a simulation — the ordinary apply path, with a reason.
   *
   *  Deliberately the *same* call `confirm` makes. There is no dedicated
   *  "apply simulation" endpoint, because a second write path is exactly how
   *  a confirmation step gets routed around (D8/D12). */
  const approveSimulation = useCallback(
    async (reason: string) => {
      if (!simulation) return;
      const applied = await run(() =>
        applyChange({
          schedule_id: simulation.schedule_id,
          operations: simulation.operations,
          reason,
          agent_reason: "אושר מתוך סימולציה",
        }),
      );
      if (applied) setSimulation(null);
    },
    [simulation, run],
  );

  const dismissSimulation = useCallback(() => setSimulation(null), []);

  const move = useCallback(
    async (input: {
      assignment_id: string;
      shift_name: string;
      slot_date: string;
      reason: string;
      schedule_id?: string;
    }) => {
      await run(() => moveAssignment(withPeriod(input)));
    },
    [run, withPeriod],
  );

  const addConstraint = useCallback(
    async (input: {
      employee: string;
      constraint_date: string;
      shift_name?: string;
      available?: boolean;
      start_time?: string;
      end_time?: string;
      is_hard?: boolean;
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
  const dismissGaps = useCallback(() => setGaps(null), []);

  // `cancelled` guards the unmount race: React's development double-mount
  // makes a component gone before the first answer arrives routine rather
  // than theoretical.
  useEffect(() => {
    let cancelled = false;
    scheduleOverview()
      .catch(() => null)
      .then((next) => {
        if (!cancelled && next) {
          setOverview(next);
          if (next.schedule?.generation.status === "running") {
            void resumeGeneration(next.schedule.id);
          }
        }
        // The opening remark, after the overview rather than beside it: the
        // calendar is what the manager came for, and the agent's greeting
        // must never be what they are waiting on.
        if (!cancelled) void brief("opened");
      });
    return () => {
      cancelled = true;
    };
  }, [brief, resumeGeneration]);

  // A watch is a poll loop, not a subscription: nothing stops it when the
  // component goes away, so leaving the area would otherwise keep a request
  // per second going for the rest of the session. The job itself carries on
  // server-side and is picked back up on the next visit.
  useEffect(() => () => {
    watching.current?.abort();
    watching.current = null;
  }, []);

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
    generation: generation ?? overview?.schedule?.generation ?? null,
    generating,
    resumeGeneration,
    cancelGeneration,
    proposal,
    briefing,
    briefing_busy: briefingBusy,
    brief,
    dismissBriefing,
    refresh,
    generate,
    generateDay,
    openBlank,
    assign,
    unassign,
    publish,
    exportSchedule,
    propose,
    confirm,
    dismissProposal,
    answer,
    answer_busy: answerBusy,
    ask,
    dismissAnswer,
    simulation,
    simulate,
    approveSimulation,
    dismissSimulation,
    move,
    focusPeriod,
    addConstraint,
    removeConstraint,
    saveProfile,
    clearError,
    gaps,
    dismissGaps,
  };
}

function inclusiveDays(first?: string, last?: string): number | null {
  if (!first || !last) return null;
  const start = new Date(`${first}T00:00:00`);
  const end = new Date(`${last}T00:00:00`);
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime()) || end < start) {
    return null;
  }
  return Math.floor((end.getTime() - start.getTime()) / 86_400_000) + 1;
}
