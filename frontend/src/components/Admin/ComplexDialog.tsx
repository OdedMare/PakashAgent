"use client";

import { AlertCircle, Check, Copy, Network, WandSparkles, X } from "lucide-react";
import { FormEvent, useEffect, useState } from "react";

import { copyText } from "@/lib/clipboard";
import {
  adminCreateComplex,
  adminDeleteComplex,
  adminResetComplexPassword,
  adminUpdateComplex,
} from "@/services/api";
import type { AdminComplex, AdminTeam } from "@/types";

import { generatePassword } from "./format";

/** Opening or editing a מכלול (D43): a name, the existing workplaces it
 *  joins, and the commander's password, which only the operator issues.
 *
 *  Each workplace keeps its own manager and its own password; the commander
 *  holds a manager's powers in every one of them. A team already in another
 *  מכלול is shown but cannot be picked here. */
export function ComplexDialog({
  complex,
  teams,
  onClose,
  onChanged,
}: {
  complex: AdminComplex | null;
  teams: AdminTeam[];
  onClose: () => void;
  onChanged: () => Promise<void>;
}) {
  const editing = complex !== null;
  const [name, setName] = useState(complex?.name ?? "");
  const [notes, setNotes] = useState(complex?.notes ?? "");
  const [picked, setPicked] = useState<Set<string>>(
    () => new Set(complex?.teams.map((team) => team.id) ?? []),
  );
  const [password, setPassword] = useState(editing ? "" : generatePassword());
  const [confirmName, setConfirmName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [handover, setHandover] = useState<{ name: string; password: string } | null>(null);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const run = async (action: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await action();
      await onChanged();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "שגיאה לא ידועה");
    } finally {
      setBusy(false);
    }
  };

  const toggle = (id: string) =>
    setPicked((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!name.trim() || busy) return;
    void run(async () => {
      const team_ids = [...picked];
      if (complex) {
        await adminUpdateComplex(complex.id, { name: name.trim(), notes, team_ids });
        if (password) {
          await adminResetComplexPassword(complex.id, password);
          setHandover({ name: name.trim(), password });
        } else onClose();
      } else {
        await adminCreateComplex({ name: name.trim(), password, team_ids });
        setHandover({ name: name.trim(), password });
      }
    });
  };

  const free = (team: AdminTeam) => !team.complex_id || team.complex_id === complex?.id;

  return (
    <div className="modal-backdrop adm-backdrop" role="presentation" onClick={onClose}>
      <section
        className="adm-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="adm-complex-title"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="adm-dialog-head">
          <span className="adm-crest is-small" aria-hidden="true">
            <Network size={17} />
          </span>
          <div>
            <h2 id="adm-complex-title">
              {handover ? "פרטי הכניסה של המפקד" : editing ? "עריכת מכלול" : "פתיחת מכלול חדש"}
            </h2>
            <p>
              {handover
                ? "מסרו למפקד המכלול את פרטי הכניסה."
                : "כמה משמרות קיימות תחת מפקד מכלול אחד. לכל משמרת נשארים מפקד המשמרת והסיסמה שלו."}
            </p>
          </div>
          <button type="button" className="adm-icon-button" onClick={onClose} aria-label="סגירה">
            <X size={17} />
          </button>
        </header>

        {handover ? (
          <HandOver {...handover} onClose={onClose} />
        ) : (
          <form className="adm-dialog-body" onSubmit={submit} autoComplete="off">
            <label className="adm-field">
              <span>שם המכלול</span>
              <input value={name} onChange={(e) => setName(e.target.value)} maxLength={80}
                placeholder="לדוגמה: מכלול צפון" autoFocus disabled={busy} />
            </label>

            <fieldset className="adm-field adm-complex-teams">
              <legend>המשמרות במכלול</legend>
              {teams.length === 0 ? <small>עדיין לא נפתח אף צוות.</small> : null}
              {teams.map((team) => (
                <label key={team.id} className={free(team) ? "" : "is-taken"}>
                  <input
                    type="checkbox"
                    checked={picked.has(team.id)}
                    onChange={() => toggle(team.id)}
                    disabled={busy || !free(team)}
                  />
                  <span>{team.name}</span>
                  {!free(team) ? <small>במכלול {team.complex_name}</small> : null}
                </label>
              ))}
            </fieldset>

            <label className="adm-field">
              <span>{editing ? "סיסמה חדשה למפקד (לא חובה)" : "סיסמת מפקד המכלול"}</span>
              <span className="adm-input-row">
                <input dir="ltr" value={password} onChange={(e) => setPassword(e.target.value)}
                  minLength={editing ? undefined : 6} maxLength={200} autoComplete="new-password"
                  data-1p-ignore="true" data-lpignore="true" disabled={busy} />
                <button type="button" className="adm-quiet-button"
                  onClick={() => setPassword(generatePassword())} disabled={busy}>
                  <WandSparkles size={14} /> חדשה
                </button>
              </span>
              <small>רק צוות משמרות זהב מנפיק ומאפס את סיסמת מפקד המכלול.</small>
            </label>

            {editing ? (
              <label className="adm-field">
                <span>הערה פנימית</span>
                <input value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={500} disabled={busy} />
              </label>
            ) : null}

            {error ? (
              <div className="adm-alert is-danger" role="alert">
                <AlertCircle size={15} /> <span>{error}</span>
              </div>
            ) : null}

            <footer className="adm-dialog-foot">
              <button type="button" className="adm-quiet-button" onClick={onClose} disabled={busy}>ביטול</button>
              <button type="submit" className="adm-gold-button"
                disabled={busy || !name.trim() || (!editing && password.length < 6) || (editing && password.length > 0 && password.length < 6)}>
                {busy ? "שומר…" : editing ? "שמירה" : "פתיחת המכלול"}
              </button>
            </footer>

            {complex ? (
              <div className="adm-complex-danger">
                <div className="adm-danger-row">
                  <span>{complex.active ? "השבתת המכלול חוסמת את מפקד המכלול. המשמרות ממשיכות כרגיל." : "המכלול מושבת."}</span>
                  <button type="button" className="adm-warn-button" disabled={busy}
                    onClick={() => void run(async () => {
                      await adminUpdateComplex(complex.id, { active: !complex.active });
                      onClose();
                    })}>
                    {complex.active ? "השבתה" : "הפעלה מחדש"}
                  </button>
                </div>
                <div className="adm-danger-row">
                  <input value={confirmName} onChange={(e) => setConfirmName(e.target.value)}
                    placeholder="הקלידו את שם המכלול למחיקה" aria-label="שם המכלול לאישור מחיקה" disabled={busy} />
                  <button type="button" className="adm-warn-button"
                    disabled={busy || confirmName.trim() !== complex.name.trim()}
                    onClick={() => void run(async () => {
                      await adminDeleteComplex(complex.id, confirmName);
                      onClose();
                    })}>
                    מחיקת המכלול
                  </button>
                </div>
                <small className="adm-muted">מחיקה מבטלת את הקיבוץ בלבד. המשמרות ונתוניהן נשארים.</small>
              </div>
            ) : null}
          </form>
        )}
      </section>
    </div>
  );
}

function HandOver({ name, password, onClose }: { name: string; password: string; onClose: () => void }) {
  const [copied, setCopied] = useState(false);
  const address = typeof window === "undefined" ? "" : window.location.origin;
  const text = [`מכלול: ${name}`, `סיסמת מפקד מכלול: ${password}`, `כניסה: ${address} ← מפקד מכלול`].join("\n");
  return (
    <div className="adm-dialog-body">
      <dl className="adm-handover">
        <div><dt>מכלול</dt><dd>{name}</dd></div>
        <div><dt>סיסמת מפקד מכלול</dt><dd dir="ltr">{password}</dd></div>
        <div><dt>כתובת כניסה</dt><dd dir="ltr">{address}</dd></div>
      </dl>
      <p className="adm-muted">בדף הכניסה בוחרים &quot;מפקד מכלול&quot;. הסיסמה מוצגת עכשיו בלבד.</p>
      <footer className="adm-dialog-foot">
        <button type="button" className="adm-quiet-button" onClick={() => void copyText(text).then(setCopied)}>
          {copied ? <><Check size={14} /> הועתק</> : <><Copy size={14} /> העתקת הפרטים</>}
        </button>
        <button type="button" className="adm-gold-button" onClick={onClose}>סיום</button>
      </footer>
    </div>
  );
}
