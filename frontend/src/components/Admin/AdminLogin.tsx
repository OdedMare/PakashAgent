"use client";

import { AlertCircle, ArrowRight, Crown, LockKeyhole } from "lucide-react";
import Link from "next/link";
import { FormEvent, useState } from "react";

/** The operator's door. One password, no team picker: the operator belongs
 *  to no team and stands above all of them (D28). */
export function AdminLogin({
  busy,
  error,
  onLogin,
}: {
  busy: boolean;
  error: string | null;
  onLogin: (password: string) => Promise<void>;
}) {
  const [password, setPassword] = useState("");

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!password || busy) return;
    await onLogin(password);
    setPassword("");
  };

  return (
    <main id="main-content" className="adm adm-gate">
      <form className="adm-gate-card" onSubmit={submit} aria-labelledby="adm-gate-title">
        <span className="adm-crest" aria-hidden="true">
          <Crown size={26} />
        </span>
        <span className="adm-eyebrow">מרכז השליטה במערכת</span>
        <h1 id="adm-gate-title">צוות משמרות זהב</h1>
        <p className="adm-gate-lede">
          פתיחת צוותים, מכסות עובדים, השבתה ומחיקה, והגדרות המערכת — הכל
          ממקום אחד.
        </p>

        <label className="adm-field">
          <span>
            <LockKeyhole size={14} aria-hidden="true" /> סיסמת ניהול
          </span>
          <input
            type="password"
            dir="ltr"
            autoFocus
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            disabled={busy}
          />
        </label>

        {error ? (
          <div className="adm-alert is-danger" role="alert">
            <AlertCircle size={15} />
            <span>{error}</span>
          </div>
        ) : null}

        <button type="submit" className="adm-gold-button" disabled={busy || !password}>
          {busy ? "בודק…" : "כניסה למרכז השליטה"}
        </button>

        <Link className="adm-back" href="/">
          <ArrowRight size={14} /> חזרה למסך הכניסה של הצוותים
        </Link>
      </form>
    </main>
  );
}
