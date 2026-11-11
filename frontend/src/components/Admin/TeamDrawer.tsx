"use client";

import { AlertCircle, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { adminTeam } from "@/services/api";
import type { AdminTeamDetail } from "@/types";

import { formatDate } from "./format";
import { DangerZone } from "./DangerZone";
import { EmployeeCount, StatusPill } from "./TeamsView";
import { AccessSection, ActivitySection, PeopleSection, SettingsSection } from "./TeamSections";

/** One workspace in full, beside the list rather than over it, so the
 *  operator keeps their place. Every write re-reads this team and the list:
 *  the counts on both move together. */
export function TeamDrawer({
  teamId,
  onClose,
  onChanged,
}: {
  teamId: string;
  onClose: () => void;
  onChanged: () => Promise<void>;
}) {
  const [team, setTeam] = useState<AdminTeamDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setTeam(await adminTeam(teamId));
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "שגיאה לא ידועה");
    }
  }, [teamId]);

  useEffect(() => {
    let cancelled = false;
    adminTeam(teamId)
      .then((next) => !cancelled && setTeam(next))
      .catch((reason) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "שגיאה לא ידועה");
      });
    return () => {
      cancelled = true;
    };
  }, [teamId]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  /** Apply a write's returned team, then refresh the list behind. */
  const changed = useCallback(
    async (next?: AdminTeamDetail) => {
      if (next) setTeam(next);
      else await load();
      await onChanged();
    },
    [load, onChanged],
  );

  return (
    <div className="adm-drawer-backdrop" role="presentation" onClick={onClose}>
      <aside
        className="adm-drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="adm-drawer-title"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="adm-drawer-head">
          <div>
            <h2 id="adm-drawer-title">{team?.name ?? "טוען…"}</h2>
            {team ? (
              <p>
                <StatusPill team={team} /> נפתח {formatDate(team.created_at)}
              </p>
            ) : null}
          </div>
          <button type="button" className="adm-icon-button" onClick={onClose} aria-label="סגירה">
            <X size={18} />
          </button>
        </header>

        {error ? (
          <div className="adm-alert is-danger" role="alert">
            <AlertCircle size={15} /> <span>{error}</span>
          </div>
        ) : null}

        {team ? (
          <div className="adm-drawer-body">
            <div className="adm-mini-stats">
              <div><small>עובדים</small><strong><EmployeeCount team={team} /></strong></div>
              <div><small>משמרות מוגדרות</small><strong>{team.shifts}</strong></div>
              <div><small>כניסות אישיות</small><strong>{team.identities}</strong></div>
              <div><small>בקשות ממתינות</small><strong>{team.pending_requests + team.pending_swaps}</strong></div>
            </div>
            {/* Keyed on the saved values, so a save (or a change made
                elsewhere) remounts the form with them rather than syncing
                props into state. */}
            <SettingsSection
              key={`${team.id}:${team.name}:${team.notes}`}
              team={team}
              onChanged={changed}
            />
            <AccessSection team={team} onChanged={changed} />
            <PeopleSection team={team} onChanged={changed} />
            <ActivitySection team={team} />
            <DangerZone
              team={team}
              onChanged={changed}
              onDeleted={async () => {
                onClose();
                await onChanged();
              }}
            />
          </div>
        ) : null}
      </aside>
    </div>
  );
}
