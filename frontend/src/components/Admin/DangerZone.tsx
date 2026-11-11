"use client";

import { AlertCircle, CirclePause, CirclePlay, Trash2 } from "lucide-react";
import { useState } from "react";

import { adminDeleteTeam, adminUpdateTeam } from "@/services/api";
import type { AdminTeamDetail } from "@/types";

/** Suspend before delete. Suspending is reversible and offered first;
 *  deleting erases the team's whole history and asks for its name typed
 *  back, because "are you sure?" is answered by reflex and retyping is not. */
export function DangerZone({
  team,
  onChanged,
  onDeleted,
}: {
  team: AdminTeamDetail;
  onChanged: (next?: AdminTeamDetail) => Promise<void>;
  onDeleted: () => Promise<void>;
}) {
  const [confirming, setConfirming] = useState(false);
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async (action: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "שגיאה לא ידועה");
    } finally {
      setBusy(false);
    }
  };

  const matches = typed.trim() === team.name.trim();

  return (
    <section className="adm-section adm-danger">
      <h3>אזור רגיש</h3>

      <div className="adm-danger-row">
        <span>
          <strong>{team.active ? "השבתת הצוות" : "הפעלת הצוות מחדש"}</strong>
          <small>
            {team.active
              ? "המנהל והעובדים לא יוכלו להיכנס, וחיבורים פתוחים ינותקו. שום מידע לא נמחק."
              : "הצוות מושבת. הפעלה מחזירה את הגישה בדיוק כפי שהייתה."}
          </small>
        </span>
        <button
          type="button"
          className={team.active ? "adm-warn-button" : "adm-gold-button"}
          disabled={busy}
          onClick={() => void run(async () => onChanged(await adminUpdateTeam(team.id, { active: !team.active })))}
        >
          {team.active ? <><CirclePause size={15} /> השבתה</> : <><CirclePlay size={15} /> הפעלה</>}
        </button>
      </div>

      <div className="adm-danger-row">
        <span>
          <strong>מחיקת הצוות לצמיתות</strong>
          <small>
            מוחק את כל הסידורים, השיבוצים, יומן השינויים, העובדים והשיחות של הצוות. אין דרך לשחזר.
          </small>
        </span>
        {confirming ? null : (
          <button type="button" className="danger-button" onClick={() => setConfirming(true)} disabled={busy}>
            <Trash2 size={15} /> מחיקה
          </button>
        )}
      </div>

      {confirming ? (
        <form
          className="adm-delete-confirm"
          onSubmit={(event) => {
            event.preventDefault();
            if (!matches) return;
            void run(async () => {
              await adminDeleteTeam(team.id, typed.trim());
              await onDeleted();
            });
          }}
        >
          <label className="adm-field">
            <span>
              להקליד <b>{team.name}</b> כדי לאשר את המחיקה
            </span>
            <input
              autoFocus
              value={typed}
              onChange={(event) => setTyped(event.target.value)}
              aria-invalid={typed.length > 0 && !matches}
            />
          </label>
          <div className="adm-section-actions">
            <button type="button" className="adm-quiet-button" onClick={() => { setConfirming(false); setTyped(""); }}>
              ביטול
            </button>
            <button type="submit" className="danger-button is-solid" disabled={!matches || busy}>
              <Trash2 size={15} /> {busy ? "מוחק…" : "מחיקה לצמיתות"}
            </button>
          </div>
        </form>
      ) : null}

      {error ? (
        <div className="adm-alert is-danger" role="alert">
          <AlertCircle size={15} /> <span>{error}</span>
        </div>
      ) : null}
    </section>
  );
}
