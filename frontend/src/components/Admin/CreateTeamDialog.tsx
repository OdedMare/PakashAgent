"use client";

import { AlertCircle, Check, Copy, Plus, WandSparkles, X } from "lucide-react";
import { FormEvent, useEffect, useState } from "react";

import { adminCreateTeam } from "@/services/api";
import type { AdminTeamDetail } from "@/types";

import { generatePassword } from "./format";

/** Opening a workspace on a team's behalf (D28).
 *
 *  Two screens: the form, then a hand-over card with what the manager needs
 *  — the team name, the password, and where to sign in. The password is shown
 *  once, here; the server keeps only its hash, and the manager can change it
 *  from their own area afterwards. */
export function CreateTeamDialog({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: () => Promise<void>;
}) {
  const [name, setName] = useState("");
  const [password, setPassword] = useState(generatePassword);
  const [limited, setLimited] = useState(true);
  const [seats, setSeats] = useState("30");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<AdminTeamDetail | null>(null);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const seatCount = Number.parseInt(seats, 10);
  const seatsValid = !limited || (Number.isInteger(seatCount) && seatCount >= 1 && seatCount <= 5000);
  const canSubmit = name.trim().length > 0 && password.length >= 6 && seatsValid && !busy;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!canSubmit) return;
    setBusy(true);
    setError(null);
    try {
      const team = await adminCreateTeam({
        name: name.trim(),
        password,
        max_employees: limited ? seatCount : null,
        notes: notes.trim(),
      });
      setCreated(team);
      await onCreated();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "שגיאה לא ידועה");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="modal-backdrop adm-backdrop" role="presentation" onClick={onClose}>
      <section
        className="adm-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="adm-create-title"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="adm-dialog-head">
          <span className="adm-crest is-small" aria-hidden="true">
            <Plus size={17} />
          </span>
          <div>
            <h2 id="adm-create-title">{created ? "הצוות נפתח" : "פתיחת צוות חדש"}</h2>
            <p>{created ? "מסרו למנהל הצוות את פרטי הכניסה." : "מרחב עבודה נפרד — ראיון, סידור והגדרות משלו."}</p>
          </div>
          <button type="button" className="adm-icon-button" onClick={onClose} aria-label="סגירה">
            <X size={17} />
          </button>
        </header>

        {created ? (
          <HandOver team={created} password={password} onClose={onClose} />
        ) : (
          <form className="adm-dialog-body" onSubmit={submit} autoComplete="off">
            <label className="adm-field">
              <span>שם הצוות</span>
              <input
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="לדוגמה: מוצב צפוני — משמרת א"
                maxLength={80}
                autoFocus
                disabled={busy}
              />
            </label>

            <label className="adm-field">
              <span>סיסמת מנהל הצוות</span>
              <span className="adm-input-row">
                <input
                  dir="ltr"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  minLength={6}
                  maxLength={200}
                  autoComplete="new-password"
                  data-1p-ignore="true"
                  data-lpignore="true"
                  disabled={busy}
                />
                <button
                  type="button"
                  className="adm-quiet-button"
                  onClick={() => setPassword(generatePassword())}
                  disabled={busy}
                >
                  <WandSparkles size={14} /> חדשה
                </button>
              </span>
              <small>לפחות 6 תווים. המנהל יוכל לשנות אותה בעצמו.</small>
            </label>

            <fieldset className="adm-field adm-seat-field">
              <legend>כמה עובדים</legend>
              <div className="adm-chips" role="radiogroup" aria-label="מכסת עובדים">
                <button type="button" role="radio" aria-checked={limited} onClick={() => setLimited(true)}>
                  מכסה קבועה
                </button>
                <button type="button" role="radio" aria-checked={!limited} onClick={() => setLimited(false)}>
                  ללא הגבלה
                </button>
              </div>
              {limited ? (
                <input
                  type="number"
                  inputMode="numeric"
                  min={1}
                  max={5000}
                  value={seats}
                  onChange={(event) => setSeats(event.target.value)}
                  aria-label="מספר העובדים המרבי"
                  aria-invalid={!seatsValid}
                  disabled={busy}
                />
              ) : null}
              <small>
                עובדים שסיימו לא נספרים. הצוות לא יוכל להוסיף עובדים מעבר למכסה; אפשר לשנות אותה בכל רגע.
              </small>
            </fieldset>

            <label className="adm-field">
              <span>הערה פנימית <em>(רשות)</em></span>
              <textarea
                rows={2}
                value={notes}
                onChange={(event) => setNotes(event.target.value)}
                placeholder="איש קשר, יחידה, תאריך חידוש…"
                maxLength={500}
                disabled={busy}
              />
              <small>נראית רק לצוות משמרות זהב.</small>
            </label>

            {error ? (
              <div className="adm-alert is-danger" role="alert">
                <AlertCircle size={15} /> <span>{error}</span>
              </div>
            ) : null}

            <footer className="adm-dialog-foot">
              <button type="button" className="adm-quiet-button" onClick={onClose} disabled={busy}>
                ביטול
              </button>
              <button type="submit" className="adm-gold-button" disabled={!canSubmit}>
                {busy ? "פותח…" : "פתיחת הצוות"}
              </button>
            </footer>
          </form>
        )}
      </section>
    </div>
  );
}

function HandOver({
  team,
  password,
  onClose,
}: {
  team: AdminTeamDetail;
  password: string;
  onClose: () => void;
}) {
  const [copied, setCopied] = useState(false);
  const address = typeof window === "undefined" ? "" : window.location.origin;
  const text = [
    `צוות: ${team.name}`,
    `סיסמת מנהל: ${password}`,
    `כניסה: ${address}`,
    team.max_employees ? `מכסת עובדים: ${team.max_employees}` : "מכסת עובדים: ללא הגבלה",
  ].join("\n");

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  };

  return (
    <div className="adm-dialog-body">
      <dl className="adm-handover">
        <div><dt>צוות</dt><dd>{team.name}</dd></div>
        <div><dt>סיסמת מנהל</dt><dd dir="ltr">{password}</dd></div>
        <div><dt>כתובת כניסה</dt><dd dir="ltr">{address}</dd></div>
        <div><dt>מכסת עובדים</dt><dd>{team.max_employees ?? "ללא הגבלה"}</dd></div>
      </dl>
      <p className="adm-muted">הסיסמה מוצגת עכשיו בלבד. אם תאבד, אפשר לקבוע חדשה מכרטיס הצוות.</p>
      <footer className="adm-dialog-foot">
        <button type="button" className="adm-quiet-button" onClick={() => void copy()}>
          {copied ? <><Check size={14} /> הועתק</> : <><Copy size={14} /> העתקת הפרטים</>}
        </button>
        <button type="button" className="adm-gold-button" onClick={onClose}>
          סיום
        </button>
      </footer>
    </div>
  );
}
