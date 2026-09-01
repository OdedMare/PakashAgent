"use client";

import {
  AlertCircle,
  CalendarDays,
  CheckCircle2,
  Plus,
  ShieldCheck,
  Users,
} from "lucide-react";
import { useEffect, useState } from "react";

import { listTeams } from "@/services/api";
import type { TeamSummary } from "@/types";

/** The boss's way in: pick an existing workspace, or open a new one.
 *
 *  Members never arrive here — they follow a share link, which logs them in
 *  without a password. That asymmetry is the whole access model (D5): the
 *  side that authors has a credential, the side that reads has a link. */
export function Login({
  busy,
  error,
  onLogin,
  onCreate,
  onDismissError,
}: {
  busy: boolean;
  error: string | null;
  onLogin: (teamId: string, password: string) => Promise<void>;
  onCreate: (name: string, password: string) => Promise<void>;
  onDismissError: () => void;
}) {
  const [teams, setTeams] = useState<TeamSummary[]>([]);
  const [creating, setCreating] = useState(false);
  const [teamId, setTeamId] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");

  useEffect(() => {
    listTeams()
      .then((rows) => {
        setTeams(rows);
        setTeamId((current) => current || rows[0]?.id || "");
        // With no workspace on the server there is nothing to log into, so
        // the form opens on "create" rather than on an empty picker.
        if (rows.length === 0) setCreating(true);
      })
      .catch(() => setTeams([]));
  }, []);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (busy) return;
    try {
      if (creating) {
        await onCreate(name.trim(), password);
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

  const canSubmit = creating
    ? name.trim().length > 0 && password.length >= 6
    : teamId.length > 0 && password.length > 0;

  return (
    <main id="main-content" className="workspace-gate">
      <section className="gate-story" aria-labelledby="gate-story-title">
        <div className="gate-story-brand">
          <span className="brand-mark" aria-hidden="true">
            <CalendarDays size={18} />
          </span>
          <span>
            <strong>משמרות זהב</strong>
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
          <h2 id="gate-form-title">{creating ? "פתיחת צוות" : "כניסת מנהל"}</h2>
        </div>
        <p className="gate-lede">
          {creating
            ? "כל צוות מקבל מרחב עבודה נפרד — ראיון, סידור והגדרות משלו."
            : "בחרו את הצוות שלכם והזינו את הסיסמה."}
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

        <label className="gate-field">
          <span>סיסמה</span>
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
          onClick={() => {
            setCreating((value) => !value);
            setPassword("");
            onDismissError();
          }}
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
