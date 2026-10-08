"use client";

import { Building2, Crown, LogOut, Moon, RefreshCw, Server, Sun } from "lucide-react";
import { useState } from "react";

import { useTheme } from "@/components/Interview/useTheme";

import { AdminLogin } from "./AdminLogin";
import { SystemView } from "./SystemView";
import { TeamsView } from "./TeamsView";
import { useAdmin } from "./useAdmin";

type Tab = "teams" | "system";

/** The צוות משמרות זהב console (D28) at `/admin`.
 *
 *  Its own surface rather than a drawer inside the management area: the
 *  operator is not a team's manager, holds a different cookie, and acts on
 *  every workspace at once. As with the workspace gate, this routing is a
 *  render of what the server decided — every `/api/admin` route is guarded by
 *  `guards.admin()` independently. */
export function AdminConsole() {
  const state = useAdmin();
  const { theme, toggle } = useTheme();
  const [tab, setTab] = useState<Tab>("teams");

  if (state.signedIn === undefined) {
    return <div className="adm adm-gate" aria-busy="true" />;
  }
  if (!state.signedIn) {
    return <AdminLogin busy={state.busy} error={state.error} onLogin={state.login} />;
  }

  return (
    <div className="adm adm-shell">
      <header className="adm-topbar">
        <div className="adm-brand">
          <span className="adm-crest is-small" aria-hidden="true">
            <Crown size={17} />
          </span>
          <span>
            <strong>צוות משמרות זהב</strong>
            <small>מרכז השליטה במערכת</small>
          </span>
        </div>

        <nav className="adm-tabs" aria-label="אזורי הניהול">
          <button
            type="button"
            aria-current={tab === "teams" ? "page" : undefined}
            onClick={() => setTab("teams")}
          >
            <Building2 size={15} /> צוותים
          </button>
          <button
            type="button"
            aria-current={tab === "system" ? "page" : undefined}
            onClick={() => setTab("system")}
          >
            <Server size={15} /> מערכת
          </button>
        </nav>

        <div className="adm-topbar-actions">
          <button
            type="button"
            className="adm-icon-button"
            onClick={toggle}
            aria-label={theme === "dark" ? "מצב בהיר" : "מצב כהה"}
            title={theme === "dark" ? "מצב בהיר" : "מצב כהה"}
          >
            {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
          </button>
          <button
            type="button"
            className="adm-icon-button"
            onClick={() => void state.reload()}
            aria-label="רענון"
            title="רענון"
          >
            <RefreshCw size={16} />
          </button>
          <button type="button" className="adm-quiet-button" onClick={() => void state.logout()}>
            <LogOut size={15} /> יציאה
          </button>
        </div>
      </header>

      <main id="main-content" className="adm-main">
        {tab === "teams" ? <TeamsView state={state} /> : <SystemView state={state} />}
      </main>
    </div>
  );
}
