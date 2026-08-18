"use client";

import { useCallback, useEffect, useState } from "react";

import {
  createTeam,
  currentWorkspace,
  loginTeam,
  logout as logoutRequest,
  openMemberLink,
  rotateMemberLink,
} from "@/services/api";
import type { TeamView } from "@/types";

/** The workspace session lives in an HttpOnly cookie, which this code cannot
 *  read by design. So "am I logged in?" is answered by asking the server —
 *  `GET /api/workspace/me` — rather than by inspecting local state that could
 *  disagree with the cookie the browser actually holds.
 *
 *  `null` means "no session"; `undefined` means "not asked yet". The
 *  distinction matters: rendering the login screen during the first check
 *  would flash it at a boss who is already signed in. */
export interface WorkspaceState {
  workspace: TeamView | null | undefined;
  busy: boolean;
  error: string | null;
  create: (name: string, password: string) => Promise<void>;
  login: (teamId: string, password: string) => Promise<void>;
  enterWithToken: (token: string) => Promise<void>;
  logout: () => Promise<void>;
  rotateLink: () => Promise<void>;
  clearError: () => void;
}

export function useWorkspace(): WorkspaceState {
  const [workspace, setWorkspace] = useState<TeamView | null | undefined>(
    undefined,
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    // A 401 is the ordinary "not logged in" case, not a failure worth
    // showing: the login screen IS the response to it. Resolved to null
    // rather than caught around the setState so the state update happens in
    // one place, off the synchronous path of whatever called this.
    const current = await currentWorkspace().catch(() => null);
    setWorkspace(current);
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

  const create = useCallback(
    async (name: string, password: string) => {
      await run(() => createTeam(name, password));
    },
    [run],
  );

  const login = useCallback(
    async (teamId: string, password: string) => {
      await run(() => loginTeam(teamId, password));
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

  // The session is an HttpOnly cookie this code cannot read, so the first
  // render has to ask the server who it is talking to. `cancelled` guards the
  // unmount race: a component gone before the answer arrives must not set
  // state, and React's development double-mount makes that path routine
  // rather than theoretical.
  useEffect(() => {
    let cancelled = false;
    currentWorkspace()
      .catch(() => null)
      .then((current) => {
        if (!cancelled) setWorkspace(current);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return {
    workspace,
    busy,
    error,
    create,
    login,
    enterWithToken,
    logout,
    rotateLink,
    clearError,
  };
}
