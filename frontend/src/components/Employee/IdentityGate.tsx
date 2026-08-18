"use client";

import { AlertCircle, KeyRound, UserCheck } from "lucide-react";
import { useState } from "react";

import type { RosterName } from "@/types";

/** Claim a name, or sign in to one already claimed.
 *
 *  Reached with a share-link session — this is the screen between "I followed
 *  the team link" and "I have a personal area"
 *  ([D14](../../../../docs/DECISIONS.md)). The share link on its own still
 *  grants the read-only roster view; claiming is an upgrade on top of it, not
 *  a replacement, so nobody is forced through here to see the schedule.
 *
 *  Names come from the workplace profile and are picked, never typed: a
 *  free-text field would let anyone holding the link invent an employee, and
 *  every downstream join is on that string. Taken names stay visible but
 *  switch to the sign-in path rather than disappearing — a person whose name
 *  is already claimed needs to log in, and hiding it would just look broken.
 */
export function IdentityGate({
  roster,
  busy,
  error,
  onClaim,
  onLogin,
  onDismissError,
}: {
  roster: RosterName[];
  busy: boolean;
  error: string | null;
  onClaim: (employee: string, passcode: string) => void;
  onLogin: (employee: string, passcode: string) => void;
  onDismissError: () => void;
}) {
  const [selected, setSelected] = useState<string | null>(null);
  const [passcode, setPasscode] = useState("");

  const chosen = roster.find((row) => row.employee === selected) ?? null;
  const claiming = chosen !== null && !chosen.claimed;
  // 4 characters, matching the backend. Checked here only to keep the button
  // honest -- the server enforces it, and this is not the security boundary.
  const ready = chosen !== null && passcode.length >= (claiming ? 4 : 1);

  const submit = () => {
    if (!chosen || !ready) return;
    if (claiming) onClaim(chosen.employee, passcode);
    else onLogin(chosen.employee, passcode);
  };

  return (
    <div className="workspace-gate">
      <div className="gate-card">
        <span className="brand-mark" aria-hidden="true">
          <UserCheck size={17} />
        </span>
        <h1>האזור האישי</h1>
        <p className="gate-lede">
          בחרו את השם שלכם מרשימת הצוות והגדירו קוד אישי. הקוד ישמור על
          השעות והבקשות שלכם.
        </p>

        {error ? (
          <div className="gate-error" role="alert" onClick={onDismissError}>
            <AlertCircle size={15} />
            <span>{error}</span>
          </div>
        ) : null}

        {roster.length === 0 ? (
          <p className="gate-lede">
            רשימת העובדים עדיין לא הוגדרה. פנו למנהל.
          </p>
        ) : (
          <>
            <div className="identity-names">
              {roster.map((row) => (
                <button
                  key={row.employee}
                  type="button"
                  className={`identity-name${
                    selected === row.employee ? " is-selected" : ""
                  }`}
                  onClick={() => {
                    setSelected(row.employee);
                    setPasscode("");
                    onDismissError();
                  }}
                >
                  <span>{row.employee}</span>
                  {/* A claimed name is not hidden: its owner still has to
                      sign in, and removing it would read as an error. */}
                  {row.claimed ? (
                    <span className="identity-badge">
                      <KeyRound size={12} /> רשום
                    </span>
                  ) : null}
                </button>
              ))}
            </div>

            {chosen ? (
              <form
                className="identity-form"
                onSubmit={(event) => {
                  event.preventDefault();
                  submit();
                }}
              >
                <label htmlFor="passcode">
                  {claiming ? "בחרו קוד אישי (4 תווים לפחות)" : "הקוד האישי"}
                </label>
                <input
                  id="passcode"
                  type="password"
                  value={passcode}
                  autoComplete={claiming ? "new-password" : "current-password"}
                  onChange={(event) => setPasscode(event.target.value)}
                  disabled={busy}
                />
                <button type="submit" disabled={!ready || busy}>
                  {claiming ? "שמירה וכניסה" : "כניסה"}
                </button>
                {claiming ? (
                  <p className="identity-hint">
                    השם הזה עדיין לא נתפס. הקוד שתבחרו עכשיו הוא זה שישמש
                    אתכם מכאן והלאה.
                  </p>
                ) : (
                  <p className="identity-hint">
                    שכחתם את הקוד? המנהל יכול לשחרר את השם כדי שתגדירו אותו
                    מחדש.
                  </p>
                )}
              </form>
            ) : null}
          </>
        )}
      </div>
    </div>
  );
}
