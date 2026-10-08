"use client";

import {
  AlertCircle,
  Building2,
  CalendarRange,
  ChevronLeft,
  Inbox,
  Plus,
  Search,
  UserCheck,
  UsersRound,
} from "lucide-react";
import { useMemo, useState } from "react";

import type { AdminTeam } from "@/types";

import { CreateTeamDialog } from "./CreateTeamDialog";
import { formatDate, formatRelative, seatState } from "./format";
import { TeamDrawer } from "./TeamDrawer";
import type { AdminState } from "./useAdmin";

type Filter = "all" | "active" | "suspended";

/** Every workspace on the server, with the numbers an operator decides by. */
export function TeamsView({ state }: { state: AdminState }) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  const [creating, setCreating] = useState(false);
  const [openId, setOpenId] = useState<string | null>(null);
  const teams = state.teams;

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return (teams ?? []).filter((team) => {
      if (filter === "active" && !team.active) return false;
      if (filter === "suspended" && team.active) return false;
      if (!needle) return true;
      return `${team.name} ${team.notes}`.toLowerCase().includes(needle);
    });
  }, [teams, query, filter]);

  return (
    <>
      <Summary teams={teams} />

      <section className="adm-panel" aria-labelledby="adm-teams-title">
        <div className="adm-panel-head">
          <div>
            <h2 id="adm-teams-title">צוותים</h2>
            <p>כל צוות הוא מרחב עבודה נפרד. רק צוות משמרות זהב פותח צוותים חדשים.</p>
          </div>
          <button type="button" className="adm-gold-button" onClick={() => setCreating(true)}>
            <Plus size={16} /> פתיחת צוות חדש
          </button>
        </div>

        <div className="adm-toolbar">
          <label className="adm-search">
            <Search size={15} aria-hidden="true" />
            <input
              type="search"
              placeholder="חיפוש לפי שם או הערה"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              aria-label="חיפוש צוות"
            />
          </label>
          <div className="adm-chips" role="radiogroup" aria-label="סינון לפי מצב">
            {(
              [
                ["all", "הכל"],
                ["active", "פעילים"],
                ["suspended", "מושבתים"],
              ] as [Filter, string][]
            ).map(([value, label]) => (
              <button
                key={value}
                type="button"
                role="radio"
                aria-checked={filter === value}
                onClick={() => setFilter(value)}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        {state.error && !teams ? (
          <div className="adm-alert is-danger" role="alert">
            <AlertCircle size={15} /> <span>{state.error}</span>
          </div>
        ) : null}

        {teams === null ? (
          <div className="adm-empty" aria-busy="true">טוען צוותים…</div>
        ) : visible.length === 0 ? (
          <div className="adm-empty">
            <Building2 size={22} aria-hidden="true" />
            <strong>{teams.length === 0 ? "עדיין לא נפתח אף צוות" : "אין צוותים שמתאימים לחיפוש"}</strong>
            {teams.length === 0 ? <span>פתחו את הצוות הראשון, וקבעו כמה עובדים הוא יכול לנהל.</span> : null}
          </div>
        ) : (
          <TeamTable teams={visible} onOpen={setOpenId} />
        )}
      </section>

      {creating ? (
        <CreateTeamDialog
          onClose={() => setCreating(false)}
          onCreated={async () => {
            await state.reload();
          }}
        />
      ) : null}

      {openId ? (
        <TeamDrawer
          teamId={openId}
          onClose={() => setOpenId(null)}
          onChanged={state.reload}
        />
      ) : null}
    </>
  );
}

function Summary({ teams }: { teams: AdminTeam[] | null }) {
  const list = teams ?? [];
  const active = list.filter((team) => team.active).length;
  const employees = list.reduce((sum, team) => sum + team.employees, 0);
  const identities = list.reduce((sum, team) => sum + team.identities, 0);
  const periods = list.reduce((sum, team) => sum + team.periods, 0);
  const pending = list.reduce((sum, team) => sum + team.pending_requests + team.pending_swaps, 0);
  const tiles = [
    { icon: Building2, label: "צוותים פעילים", value: `${active}`, hint: `מתוך ${list.length}` },
    { icon: UsersRound, label: "עובדים במערכת", value: `${employees}`, hint: "בכל הצוותים" },
    { icon: UserCheck, label: "עובדים עם כניסה אישית", value: `${identities}`, hint: "שמות שנתבעו" },
    { icon: CalendarRange, label: "תקופות סידור", value: `${periods}`, hint: "טיוטות ופורסמו" },
    { icon: Inbox, label: "בקשות ממתינות", value: `${pending}`, hint: "אילוצים והחלפות" },
  ];
  return (
    <section className="adm-tiles" aria-label="תמונת מצב">
      {tiles.map(({ icon: Icon, label, value, hint }) => (
        <div className="adm-tile" key={label}>
          <span className="adm-tile-icon" aria-hidden="true">
            <Icon size={17} />
          </span>
          <span className="adm-tile-label">{label}</span>
          <strong>{teams === null ? "—" : value}</strong>
          <small>{hint}</small>
        </div>
      ))}
    </section>
  );
}

function TeamTable({ teams, onOpen }: { teams: AdminTeam[]; onOpen: (id: string) => void }) {
  return (
    <div className="adm-table">
      {/* Visual column heads only; each row is one button that names its
          team, so a screen reader hears a list of teams rather than a grid. */}
      <div className="adm-row is-head" aria-hidden="true">
        <span>צוות</span>
        <span>מצב</span>
        <span>עובדים / מכסה</span>
        <span>כניסות אישיות</span>
        <span>תקופות</span>
        <span>פעילות אחרונה</span>
        <span />
      </div>
      <ul className="adm-rows" aria-label="רשימת הצוותים">
      {teams.map((team) => (
        <li key={team.id}>
        <button
          type="button"
          className={`adm-row${team.active ? "" : " is-suspended"}`}
          onClick={() => onOpen(team.id)}
        >
          <span className="adm-team-name">
            <strong>{team.name}</strong>
            <small>{team.notes || `נפתח ${formatDate(team.created_at)}`}</small>
          </span>
          <span>
            <StatusPill team={team} />
          </span>
          <span>
            <SeatMeter used={team.employees} cap={team.max_employees} />
          </span>
          <span data-label="כניסות אישיות">{team.identities}</span>
          <span data-label="תקופות">
            {team.periods}
            {team.published ? <small> · {team.published} פורסמו</small> : null}
          </span>
          <span data-label="פעילות">{formatRelative(team.last_activity)}</span>
          <span className="adm-row-open" aria-hidden="true">
            <ChevronLeft size={16} />
          </span>
        </button>
        </li>
      ))}
      </ul>
    </div>
  );
}

export function StatusPill({ team }: { team: AdminTeam }) {
  if (!team.active) return <span className="adm-pill is-off">מושבת</span>;
  if (!team.has_profile) return <span className="adm-pill is-setup">בהקמה</span>;
  return <span className="adm-pill is-on">פעיל</span>;
}

export function SeatMeter({ used, cap }: { used: number; cap: number | null }) {
  const state = seatState(used, cap);
  const share = cap ? Math.min(100, Math.round((used / cap) * 100)) : 0;
  return (
    <span className={`adm-seats is-${state}`}>
      <span className="adm-seats-text">
        <b>{used}</b> / {cap === null ? "ללא הגבלה" : cap}
      </span>
      {cap !== null ? (
        <span className="adm-seats-bar" aria-hidden="true">
          <i style={{ width: `${share}%` }} />
        </span>
      ) : null}
    </span>
  );
}
