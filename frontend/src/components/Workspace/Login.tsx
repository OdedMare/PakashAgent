"use client";

import {
  AlertCircle,
  CalendarDays,
  CheckCircle2,
  Plus,
  ShieldCheck,
  UserCircle,
  UserCog,
  Users,
} from "lucide-react";
import { useEffect, useState } from "react";

import { listTeams } from "@/services/api";
import type { TeamSummary } from "@/types";

/** Which door the visitor is standing at. `create` is not a door into an
 *  existing team, so it hides the picker. */
type Mode = "boss" | "worker" | "create";

/** The front door: pick the team, then come in as its manager or as a worker.
 *
 *  The two doors take different credentials on purpose. The manager types
 *  the team password (D10). A worker types the name they claimed and their
 *  personal passcode (D14) — and only that: *claiming* a name still needs the
 *  share link, because this screen is open to anyone and the team list above
 *  it is public (D25). The name is typed rather than picked for the same
 *  reason: a picker here would publish every team's roster. */
export function Login({
  busy,
  error,
  onLogin,
  onEmployeeLogin,
  onCreate,
  onDismissError,
}: {
  busy: boolean;
  error: string | null;
  onLogin: (teamId: string, password: string) => Promise<void>;
  onEmployeeLogin: (
    teamId: string,
    employee: string,
    passcode: string,
  ) => Promise<void>;
  onCreate: (name: string, password: string) => Promise<void>;
  onDismissError: () => void;
}) {
  const [teams, setTeams] = useState<TeamSummary[]>([]);
  const [mode, setMode] = useState<Mode>("boss");
  const [teamId, setTeamId] = useState("");
  const [name, setName] = useState("");
  const [employee, setEmployee] = useState("");
  const [password, setPassword] = useState("");
  const creating = mode === "create";

  const switchMode = (next: Mode) => {
    setMode(next);
    setPassword("");
    onDismissError();
  };

  useEffect(() => {
    listTeams()
      .then((rows) => {
        setTeams(rows);
        setTeamId((current) => current || rows[0]?.id || "");
        // With no workspace on the server there is nothing to log into, so
        // the form opens on "create" rather than on an empty picker.
        if (rows.length === 0) setMode("create");
      })
      .catch(() => setTeams([]));
  }, []);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (busy) return;
    try {
      if (mode === "create") {
        await onCreate(name.trim(), password);
      } else if (mode === "worker") {
        await onEmployeeLogin(teamId, employee.trim(), password);
      } else {
        await onLogin(teamId, password);
      }
      setPassword("");
    } catch {
      // The hook already surfaced the message; keeping the typed password
      // would only invite a second submit of the same wrong value.
      setPassword("");
    }
  };

  const canSubmit =
    mode === "create"
      ? name.trim().length > 0 && password.length >= 6
      : mode === "worker"
        ? teamId.length > 0 && employee.trim().length > 0 && password.length > 0
        : teamId.length > 0 && password.length > 0;

  return (
    <main id="main-content" className="workspace-gate">
      <section className="gate-story" aria-labelledby="gate-story-title">
        <div className="gate-story-brand">
          <span className="brand-mark" aria-hidden="true">
            <CalendarDays size={18} />
          </span>
          <span>
            <strong>פקש</strong>
            <small>ניהול סידורי עבודה</small>
          </span>
        </div>

        <div className="gate-story-copy">
          <span className="gate-eyebrow">חדר השיבוץ של הצוות</span>
          <h1 id="gate-story-title">רואים את כל השבוע. מטפלים במה שחשוב.</h1>
          <p>
            בונים, בודקים ומפרסמים סידור אחד ברור — עם הסבר לכל שינוי ותמונה
            מלאה של הכיסוי לפני שהצוות מקבל אותו.
          </p>
        </div>

        <div className="gate-week-preview" aria-hidden="true">
          <div className="gate-week-head">
            <strong>מוכנות השבוע</strong>
            <span><i /> מעודכן עכשיו</span>
          </div>
          <div className="gate-week-days">
            <span><b>א׳</b><i /></span>
            <span><b>ב׳</b><i /></span>
            <span className="is-attention"><b>ג׳</b><i /></span>
            <span><b>ד׳</b><i /></span>
            <span><b>ה׳</b><i /></span>
            <span><b>ו׳</b><i /></span>
            <span className="is-quiet"><b>ש׳</b><i /></span>
          </div>
          <div className="gate-week-summary">
            <span><small>כיסוי</small><strong>92%</strong></span>
            <span><small>דורש טיפול</small><strong>2</strong></span>
            <span><small>בקשות חדשות</small><strong>3</strong></span>
          </div>
        </div>

        <div className="gate-trust">
          <span><ShieldCheck size={14} /> כל שינוי נשאר לאישור</span>
          <span><CheckCircle2 size={14} /> האזהרות מוצגות לפני הפרסום</span>
        </div>
      </section>

      <form className="gate-card" onSubmit={submit} aria-labelledby="gate-form-title">
        <div className="gate-form-head">
          <span>{creating ? "סביבת עבודה חדשה" : "כניסה מאובטחת"}</span>
          <h2 id="gate-form-title">
            {creating ? "פתיחת צוות" : mode === "worker" ? "כניסת עובד/ת" : "כניסת מנהל"}
          </h2>
        </div>
        <p className="gate-lede">
          {creating
            ? "כל צוות מקבל מרחב עבודה נפרד — ראיון, סידור והגדרות משלו."
            : "בחרו את הצוות, ואז היכנסו כמנהל או כעובד/ת."}
        </p>

        {creating ? (
          <label className="gate-field">
            <span>שם הצוות</span>
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="לדוגמה: צוות תפעול"
              maxLength={80}
              autoComplete="organization"
              disabled={busy}
            />
          </label>
        ) : (
          <label className="gate-field">
            <span>צוות</span>
            <select
              value={teamId}
              onChange={(event) => setTeamId(event.target.value)}
              disabled={busy || teams.length === 0}
            >
              {teams.map((team) => (
                <option key={team.id} value={team.id}>
                  {team.name}
                </option>
              ))}
            </select>
          </label>
        )}

        {creating ? null : (
          <div className="gate-doors" role="radiogroup" aria-label="סוג כניסה">
            <button
              type="button"
              role="radio"
              aria-checked={mode === "boss"}
              className={`gate-door${mode === "boss" ? " is-selected" : ""}`}
              onClick={() => switchMode("boss")}
              disabled={busy}
            >
              <UserCog size={18} />
              <span>מנהל</span>
            </button>
            <button
              type="button"
              role="radio"
              aria-checked={mode === "worker"}
              className={`gate-door${mode === "worker" ? " is-selected" : ""}`}
              onClick={() => switchMode("worker")}
              disabled={busy}
            >
              <UserCircle size={18} />
              <span>עובד/ת</span>
            </button>
          </div>
        )}

        {mode === "worker" ? (
          <label className="gate-field">
            <span>השם שלך</span>
            <input
              value={employee}
              onChange={(event) => setEmployee(event.target.value)}
              placeholder="כפי שרשום בצוות"
              maxLength={120}
              autoComplete="username"
              disabled={busy}
            />
          </label>
        ) : null}

        <label className="gate-field">
          <span>{mode === "worker" ? "קוד אישי" : "סיסמה"}</span>
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete={creating ? "new-password" : "current-password"}
            disabled={busy}
          />
          {creating ? (
            <small className="gate-hint">לפחות 6 תווים.</small>
          ) : null}
          {mode === "worker" ? (
            <small className="gate-hint">
              עדיין אין לכם קוד אישי? פתחו את קישור הצוות שקיבלתם מהמנהל
              ובחרו בו את השם שלכם.
            </small>
          ) : null}
        </label>

        {error ? (
          <div className="gate-error" role="alert">
            <AlertCircle size={15} />
            <span>{error}</span>
          </div>
        ) : null}

        <button
          type="submit"
          className="start-button"
          disabled={busy || !canSubmit}
        >
          {busy ? "רגע…" : creating ? "פתחו מרחב עבודה" : "כניסה"}
        </button>

        <button
          type="button"
          className="gate-switch"
          onClick={() => switchMode(creating ? "boss" : "create")}
          disabled={busy}
        >
          {creating ? (
            <>
              <Users size={14} /> יש לי כבר צוות
            </>
          ) : (
            <>
              <Plus size={14} /> פתיחת צוות חדש
            </>
          )}
        </button>
      </form>
    </main>
  );
}
