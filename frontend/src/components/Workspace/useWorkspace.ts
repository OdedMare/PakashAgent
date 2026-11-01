"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  commanderLogin,
  commanderLogout,
  commanderMe,
  currentWorkspace,
  enterComplexTeam,
  leaveComplexTeam,
  employeeSignIn,
  errorStatus,
  loginTeam,
  logout as logoutRequest,
  onSessionLost,
  openMemberLink,
  rotateMemberLink,
} from "@/services/api";
import type { CommanderView, TeamView } from "@/types";

/** The workspace session lives in an HttpOnly cookie, which this code cannot
 *  read by design. So "am I logged in?" is answered by asking the server —
 *  `GET /api/workspace/me` — rather than by inspecting local state that could
 *  disagree with the cookie the browser actually holds.
 *
 *  `null` means "no session"; `undefined` means "not asked yet". The
 *  distinction matters: rendering the login screen during the first check
 *  would flash it at a boss who is already signed in. */
interface WorkspaceState {
  workspace: TeamView | null | undefined;
  /** The מכלול commander's own session (D43), separate from the team one:
   *  `undefined` not asked yet, `null` none. */
  commander: CommanderView | null | undefined;
  commanderLogin: (complexId: string, password: string) => Promise<void>;
  /** The commander chose to work inside a משמרת. The מכלול screen may hold
   *  a משמרת session of its own (its agent, statistics and changes pages),
   *  so a commander-marked session alone does not mean "inside". */
  inside: boolean;
  /** Open one workplace with a manager's powers. */
  enterTeam: (teamId: string) => Promise<void>;
  /** Back from a workplace to the combined board. */
  leaveTeam: () => Promise<void>;
  /** Sign the commander out altogether. */
  commanderLogout: () => Promise<void>;
  busy: boolean;
  error: string | null;
  login: (teamId: string, password: string) => Promise<void>;
  /** The worker's front door: a name already claimed, and its passcode. */
  employeeLogin: (
    teamId: string,
    employee: string,
    passcode: string,
  ) => Promise<void>;
  enterWithToken: (token: string) => Promise<void>;
  logout: () => Promise<void>;
  rotateLink: () => Promise<void>;
  /** Re-read `/api/workspace/me`. Exposed so a surface that wrote something
   *  the router switches on — setup writing a profile — can have the
   *  answer refreshed before it hands control back. */
  refresh: () => Promise<void>;
  clearError: () => void;
}

/** Which משמרת the מכלול commander chose to work inside, for this tab only.
 *  The signed cookie cannot say it: the מכלול screen's own agent, statistics
 *  and changes pages hold a משמרת session too. A per-tab convenience — lost,
 *  it only means a reload shows the מכלול screen. */
const INSIDE_KEY = "pakash-commander-inside";

function rememberInside(teamId: string | null) {
  try {
    if (teamId) sessionStorage.setItem(INSIDE_KEY, teamId);
    else sessionStorage.removeItem(INSIDE_KEY);
  } catch {
    // Storage refused (a private window): nothing to remember.
  }
}

function wasInside(teamId: string | undefined): boolean {
  try {
    return Boolean(teamId) && sessionStorage.getItem(INSIDE_KEY) === teamId;
  } catch {
    return false;
  }
}

export function useWorkspace(): WorkspaceState {
  const [workspace, setWorkspace] = useState<TeamView | null | undefined>(
    undefined,
  );
  const [commander, setCommander] = useState<CommanderView | null | undefined>(
    undefined,
  );
  const [inside, setInside] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    // A 401 is the ordinary "not logged in" case, not a failure worth
    // showing: the login screen IS the response to it. Resolved to null
    // rather than caught around the setState so the state update happens in
    // one place, off the synchronous path of whatever called this.
    const [current, chief] = await Promise.all([
      currentWorkspace().catch(() => null),
      commanderMe().catch(() => null),
    ]);
    setWorkspace(current);
    setCommander(chief);
  }, []);

  const run = useCallback(
    async (action: () => Promise<unknown>) => {
      setBusy(true);
      setError(null);
      try {
        await action();
        await refresh();
      } catch (reason) {
        setError(reason instanceof Error ? reason.message : "שגיאה לא ידועה");
        throw reason;
      } finally {
        setBusy(false);
      }
    },
    [refresh],
  );

  const login = useCallback(
    async (teamId: string, password: string) => {
      await run(() => loginTeam(teamId, password));
    },
    [run],
  );

  const employeeLogin = useCallback(
    async (teamId: string, employee: string, passcode: string) => {
      await run(() => employeeSignIn({ teamId, employee, passcode }));
    },
    [run],
  );

  const enterWithToken = useCallback(
    async (token: string) => {
      await run(() => openMemberLink(token));
    },
    [run],
  );

  const logout = useCallback(async () => {
    await logoutRequest().catch(() => undefined);
    // Cleared locally rather than re-fetched: the cookie is gone, so `me`
    // would only 401 its way back to the same null after another round trip.
    setWorkspace(null);
    setError(null);
  }, []);

  const rotateLink = useCallback(async () => {
    await run(() => rotateMemberLink());
  }, [run]);

  const clearError = useCallback(() => setError(null), []);

  const loginCommander = useCallback(
    async (complexId: string, password: string) => {
      await run(() => commanderLogin(complexId, password));
    },
    [run],
  );

  const enterTeam = useCallback(
    async (teamId: string) => {
      await run(() => enterComplexTeam(teamId));
      rememberInside(teamId);
      setInside(true);
    },
    [run],
  );

  const leaveTeam = useCallback(async () => {
    await run(() => leaveComplexTeam());
    rememberInside(null);
    setInside(false);
  }, [run]);

  const logoutCommander = useCallback(async () => {
    await commanderLogout().catch(() => undefined);
    setCommander(null);
    rememberInside(null);
    setInside(false);
    await refresh();
  }, [refresh]);

  // The session is an HttpOnly cookie this code cannot read, so the first
  // render has to ask the server who it is talking to. `cancelled` guards the
  // unmount race: a component gone before the answer arrives must not set
  // state, and React's development double-mount makes that path routine
  // rather than theoretical.
  useEffect(() => {
    let cancelled = false;
    Promise.all([
      currentWorkspace().catch(() => null),
      commanderMe().catch(() => null),
    ]).then(([current, chief]) => {
      if (cancelled) return;
      setWorkspace(current);
      setCommander(chief);
      // A reload inside a משמרת resumes there; one on the מכלול screen
      // stays there.
      setInside(Boolean(current?.commander) && wasInside(current?.id));
    });
    return () => {
      cancelled = true;
    };
  }, []);

  // A read refused for want of a session means the cookie died under an open
  // screen. Asking `/me` again is what decides it: only its own 401 clears
  // the workspace, so a network blip or a 401 from a guard the visitor's
  // role simply does not pass leaves them where they are. Clearing it
  // unmounts the area, and with it every poller that was still asking.
  // Several pollers fail at once, so one check stands in for all of them.
  const checking = useRef(false);
  useEffect(() => onSessionLost(() => {
    if (checking.current) return;
    checking.current = true;
    currentWorkspace()
      .then(() => undefined, (reason) => {
        if (errorStatus(reason) === 401) setWorkspace(null);
      })
      .finally(() => {
        checking.current = false;
      });
  }), []);

  return {
    workspace,
    commander,
    inside,
    commanderLogin: loginCommander,
    enterTeam,
    leaveTeam,
    commanderLogout: logoutCommander,
    busy,
    error,
    login,
    employeeLogin,
    enterWithToken,
    logout,
    rotateLink,
    refresh,
    clearError,
  };
}
