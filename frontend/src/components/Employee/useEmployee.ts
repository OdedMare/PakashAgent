"use client";

import { useCallback, useEffect, useState } from "react";

import {
  acknowledgeChanges,
  claimIdentity,
  employeeLogin,
  employeeLogout,
  employeeMe,
  employeeRoster,
  submitConstraintRequest,
  withdrawConstraintRequest,
} from "@/services/api";
import type { EmployeeView, RosterName } from "@/types";

/** State for the employee's own area.
 *
 *  `view === undefined` is "not asked yet" and `null` is "asked, and there is
 *  no identity" — the same three-state convention `useWorkspace` uses. The
 *  distinction matters for the same reason: collapsing them flashes the claim
 *  screen at someone who is already signed in.
 *
 *  Nothing here sends the employee's name to a read endpoint. The server takes
 *  it from the signed cookie, so this hook cannot ask for anyone else's data
 *  even if it wanted to (D14). */
export function useEmployee() {
  const [view, setView] = useState<EmployeeView | null | undefined>(undefined);
  const [roster, setRoster] = useState<RosterName[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setView(await employeeMe());
    } catch {
      // A 401 here is the ordinary case, not a failure: it means this
      // visitor holds a share link and has not claimed a name yet.
      setView(null);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  // The roster is only needed while signed out, so it is fetched when the
  // gate is actually showing rather than on every mount.
  useEffect(() => {
    if (view !== null) return;
    employeeRoster()
      .then((result) => setRoster(result.names))
      .catch(() => setRoster([]));
  }, [view]);

  const run = useCallback(
    async <T,>(action: () => Promise<T>): Promise<T | undefined> => {
      setBusy(true);
      setError(null);
      try {
        return await action();
      } catch (reason) {
        setError(reason instanceof Error ? reason.message : "שגיאה");
        return undefined;
      } finally {
        setBusy(false);
      }
    },
    [],
  );

  const claim = useCallback(
    async (employee: string, passcode: string) => {
      const done = await run(() => claimIdentity({ employee, passcode }));
      if (done) await load();
    },
    [run, load],
  );

  const login = useCallback(
    async (employee: string, passcode: string) => {
      const done = await run(() => employeeLogin({ employee, passcode }));
      if (done) await load();
    },
    [run, load],
  );

  const logout = useCallback(async () => {
    await run(() => employeeLogout());
    setView(null);
  }, [run]);

  const submit = useCallback(
    async (body: {
      constraint_date: string;
      shift_name?: string;
      available?: boolean;
      reason?: string;
    }) => {
      const done = await run(() => submitConstraintRequest(body));
      // Reload rather than pushing the returned row into local state: the
      // submission may have superseded an earlier pending request, and the
      // server is the only thing that knows which.
      if (done) await load();
      return Boolean(done);
    },
    [run, load],
  );

  /** Mark the changes on screen as read (D16).
   *
   *  Called from the panel that renders them rather than on load, so the
   *  badge clears when the employee has actually looked at what moved — not
   *  merely because they opened the app.
   *
   *  The local view is settled directly instead of reloading: the only thing
   *  that changed is this person's own acknowledgement, and a full refetch
   *  would visibly redraw the whole screen to clear one badge. A failure
   *  leaves the badge standing, which is the safe direction — an unread
   *  change shown twice costs nothing, one silently cleared costs the
   *  feature.
   */
  const acknowledge = useCallback(async () => {
    try {
      await acknowledgeChanges();
    } catch {
      return;
    }
    setView((current) =>
      current
        ? {
            ...current,
            unseen: 0,
            changes: current.changes.map((row) => ({ ...row, is_new: false })),
          }
        : current,
    );
  }, []);

  const withdraw = useCallback(
    async (requestId: string) => {
      const done = await run(() => withdrawConstraintRequest(requestId));
      if (done) await load();
    },
    [run, load],
  );

  return {
    view,
    roster,
    busy,
    error,
    claim,
    login,
    logout,
    submit,
    withdraw,
    acknowledge,
    reload: load,
    clearError: () => setError(null),
  };
}
