"use client";

import { useCallback, useEffect, useState } from "react";

import {
  adminLogin,
  adminLogout,
  adminMe,
  adminOverview,
  adminTeams,
} from "@/services/api";
import type { AdminOverview, AdminTeam } from "@/types";

/** The operator console's session and its two lists.
 *
 *  Like the workspace gate, "am I signed in?" is asked of the server
 *  (`/api/admin/me`) because the cookie is HttpOnly. `undefined` is "not asked
 *  yet" and `false` is "no operator session", so the login card never flashes
 *  at someone who is already in. */
export function useAdmin() {
  const [signedIn, setSignedIn] = useState<boolean | undefined>(undefined);
  const [teams, setTeams] = useState<AdminTeam[] | null>(null);
  const [overview, setOverview] = useState<AdminOverview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      const [nextTeams, nextOverview] = await Promise.all([
        adminTeams(),
        adminOverview(),
      ]);
      setTeams(nextTeams);
      setOverview(nextOverview);
      setError(null);
    } catch (reason) {
      // An expired operator cookie lands here; going back to the login card
      // is the honest answer to it.
      const message = reason instanceof Error ? reason.message : "שגיאה לא ידועה";
      setError(message);
      adminMe().catch(() => setSignedIn(false));
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    adminMe()
      .then(() => !cancelled && setSignedIn(true))
      .catch(() => !cancelled && setSignedIn(false));
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (signedIn) void reload();
  }, [signedIn, reload]);

  const login = useCallback(async (password: string) => {
    setBusy(true);
    setError(null);
    try {
      await adminLogin(password);
      setSignedIn(true);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "שגיאה לא ידועה");
    } finally {
      setBusy(false);
    }
  }, []);

  const logout = useCallback(async () => {
    await adminLogout().catch(() => undefined);
    setSignedIn(false);
    setTeams(null);
    setOverview(null);
  }, []);

  return {
    signedIn,
    teams,
    overview,
    busy,
    error,
    login,
    logout,
    reload,
    clearError: () => setError(null),
  };
}

export type AdminState = ReturnType<typeof useAdmin>;
